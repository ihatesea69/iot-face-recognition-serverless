import boto3
import json
import os
import shutil
import time
import zipfile
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

# Configuration
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "nghi-face-recognition-bucket") # Make sure this matches .env
REKOGNITION_COLLECTION_ID = os.getenv("REKOGNITION_COLLECTION_ID", "home-security-faces")
MONGODB_URI = os.getenv("MONGODB_URI") # Must be set in .env or passed

LAMBDA_ROLE_NAME = "HomeSecurityLambdaRole"
PROCESS_FUNC_NAME = "HomeSecurity_ProcessImage"
MANAGE_FUNC_NAME = "HomeSecurity_ManageFaces"

iam = boto3.client("iam")
lambda_client = boto3.client("lambda", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)

def create_lambda_role():
    print(f"--- Creating IAM Role: {LAMBDA_ROLE_NAME} ---")
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }
    
    try:
        role = iam.create_role(
            RoleName=LAMBDA_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy)
        )
        print(f"✅ Role created: {role['Role']['Arn']}")
        
        # Attach basic permissions + S3 + Rekognition
        policies = [
            "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            "arn:aws:iam::aws:policy/AmazonS3FullAccess",
            "arn:aws:iam::aws:policy/AmazonRekognitionFullAccess"
        ]
        
        for policy in policies:
            iam.attach_role_policy(RoleName=LAMBDA_ROLE_NAME, PolicyArn=policy)
            print(f"   Attached policy: {policy.split('/')[-1]}")
            
        print("⏳ Waiting 10s for role propagation...")
        time.sleep(10)
        return role['Role']['Arn']
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'EntityAlreadyExists':
            print(f"ℹ️ Role already exists.")
            role = iam.get_role(RoleName=LAMBDA_ROLE_NAME)
            return role['Role']['Arn']
        else:
            print(f"❌ Error creating role: {e}")
            raise

def zip_folder(folder_path, output_path):
    print(f"📦 Zipping {folder_path} -> {output_path}")
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, folder_path)
                zipf.write(file_path, arcname)

def wait_for_update(func_name):
    print(f"⏳ Waiting for function update to complete...")
    for _ in range(30):
        try:
            conf = lambda_client.get_function_configuration(FunctionName=func_name)
            status = conf.get('LastUpdateStatus', 'Successful')
            if status == 'Successful':
                return
            elif status == 'Failed':
                raise Exception(f"Function update failed: {conf.get('LastUpdateStatusReason')}")
        except ClientError:
            pass
        time.sleep(2)
    print("⚠️ Timed out waiting for update, proceeding anyway...")

def deploy_function(func_name, code_path, handler, env_vars, role_arn):
    print(f"\n--- Deploying Function: {func_name} ---")
    
    with open(code_path, 'rb') as f:
        zip_content = f.read()

    try:
        lambda_client.create_function(
            FunctionName=func_name,
            Runtime='python3.12',
            Role=role_arn,
            Handler=handler,
            Code={'ZipFile': zip_content},
            Timeout=30,
            Environment={'Variables': env_vars},
            Architectures=['arm64'] # Cheaper/Faster
        )
        print(f"✅ Function created: {func_name}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceConflictException':
            print(f"ℹ️ Function exists. Updating code...")
            lambda_client.update_function_code(
                FunctionName=func_name,
                ZipFile=zip_content
            )
            wait_for_update(func_name)
            
            print(f"ℹ️ Updating configuration...")
            lambda_client.update_function_configuration(
                FunctionName=func_name,
                Environment={'Variables': env_vars}
            )
            wait_for_update(func_name)
            print(f"✅ Function updated: {func_name}")
        else:
            print(f"❌ Error deploying function: {e}")
            raise

def setup_s3_trigger(func_name, bucket_name):
    print(f"\n--- Configuring S3 Trigger for {bucket_name} ---")
    
    # 1. Add permission for S3 to invoke Lambda
    try:
        # Try to remove it first to ensure update (policy clean)
        try:
            lambda_client.remove_permission(
                FunctionName=func_name,
                StatementId="s3-invoke-trigger"
            )
            print("ℹ️ Removed existing permission.")
        except ClientError:
            pass # Did not exist
        
        print("⏳ Waiting 2s for permission deletion...")
        time.sleep(2)

        lambda_client.add_permission(
            FunctionName=func_name,
            StatementId="s3-invoke-trigger",
            Action="lambda:InvokeFunction",
            Principal="s3.amazonaws.com",
            SourceArn=f"arn:aws:s3:::{bucket_name}"
        )
    except ClientError as e:
        if e.response['Error']['Code'] != 'ResourceConflictException':
             print(f"⚠️ Could not add S3 permission: {e}")
        else:
             print(f"ℹ️ Permission already exists.")

    print("⏳ Waiting 5s for permission propagation...")
    time.sleep(5)

    # 2. Configure Bucket Notification
    notification_config = {
        'LambdaFunctionConfigurations': [
            {
                'LambdaFunctionArn': lambda_client.get_function(FunctionName=func_name)['Configuration']['FunctionArn'],
                'Events': ['s3:ObjectCreated:*'],
                 'Filter': {
                    'Key': {
                        'FilterRules': [{'Name': 'prefix', 'Value': 'captures/'}, {'Name': 'suffix', 'Value': '.jpg'}]
                    }
                }
            }
        ]
    }
    
    s3.put_bucket_notification_configuration(
        Bucket=bucket_name,
        NotificationConfiguration=notification_config
    )
    print(f"✅ S3 Trigger configured")

def setup_function_url(func_name):
    print(f"\n--- Configuring Function URL for {func_name} ---")
    try:
        response = lambda_client.create_function_url_config(
            FunctionName=func_name,
            AuthType='NONE',
            Cors={
                'AllowOrigins': ['*'],
                'AllowMethods': ['*'],
                'AllowHeaders': ['content-type'],
                'MaxAge': 300
            }
        )
        url = response['FunctionUrl']
        print(f"✅ Function URL created: {url}")
        
        # Add permission for public access
        try:
             lambda_client.add_permission(
                FunctionName=func_name,
                StatementId="FunctionURLAllowPublicAccess",
                Action="lambda:InvokeFunctionUrl",
                Principal="*",
                FunctionUrlAuthType="NONE"
            )
        except ClientError:
            pass # Likely already exists
            
        return url
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceConflictException':
            response = lambda_client.get_function_url_config(FunctionName=func_name)
            url = response['FunctionUrl']
            print(f"ℹ️ Function URL already exists: {url}")
            return url
        else:
            print(f"❌ Error creating function URL: {e}")
            return None

def main():
    if not MONGODB_URI:
        print("❌ MONGODB_URI is missing in environment variables (.env)")
        return

    # Install dependencies to build folder
    # Note: We are deploying raw handler + pymongo. 
    # Lambda environment doesn't have pymongo. We must zip site-packages.
    # For simplicity in this script, we assumes dependencies are installed in a 'package' folder
    # OR we rely on Lambda Layers.
    # BETTER APPROACH: We just warn user to install dependencies to a target folder?
    # Automated approach:
    print("⚠️  NOTE: This script assumes 'pymongo' and 'boto3' are available or we need to package them.")
    print("   For a robust production deployment, use AWS SAM.")
    print("   Attempting simple deployment... (Make sure to build dependencies if running on Cloud)")
    
    # 1. Create Role
    role_arn = create_lambda_role()
    
    # 2. Deploy Process Image
    # Need to verify if 'lambda/process_image' has dependencies. 
    # Ideally we should run `pip install -r lambda/process_image/requirements.txt -t lambda/process_image/`
    # User can run this manually or we can try subprocess.
    
    import subprocess
    print("\n📦 Installing dependencies for Process Image...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "lambda/process_image/requirements.txt", "-t", "lambda/process_image/"])
    
    zip_folder("lambda/process_image", "process_image.zip")
    
    deploy_function(
        PROCESS_FUNC_NAME, 
        "process_image.zip", 
        "handler.handler", 
        {
            "MONGODB_URI": MONGODB_URI, 
            "REKOGNITION_COLLECTION_ID": REKOGNITION_COLLECTION_ID
        },
        role_arn
    )
    
    setup_s3_trigger(PROCESS_FUNC_NAME, S3_BUCKET_NAME)
    
    # 3. Deploy Manage Faces
    print("\n📦 Installing dependencies for Manage Faces...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "lambda/manage_faces/requirements.txt", "-t", "lambda/manage_faces/"])
    
    zip_folder("lambda/manage_faces", "manage_faces.zip")
    
    deploy_function(
        MANAGE_FUNC_NAME,
        "manage_faces.zip",
        "handler.handler",
         {
            "MONGODB_URI": MONGODB_URI, 
            "REKOGNITION_COLLECTION_ID": REKOGNITION_COLLECTION_ID,
            "S3_BUCKET_NAME": S3_BUCKET_NAME
        },
        role_arn
    )
    
    url = setup_function_url(MANAGE_FUNC_NAME)
    
    if url:
        print(f"\n✅ SETUP COMPLETE!")
        print(f"👉 Update NEXT_PUBLIC_LAMBDA_MANAGE_FACES_URL in dashboard/.env with:")
        print(f"   {url}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # Reload from env to be sure
    MONGODB_URI = os.getenv("MONGODB_URI") 
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME") or S3_BUCKET_NAME
    
    import sys
    main()
