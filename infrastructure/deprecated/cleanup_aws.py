import boto3
import os
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "nghi-face-recognition-bucket")
REKOGNITION_COLLECTION_ID = os.getenv("REKOGNITION_COLLECTION_ID", "home-security-faces")
LAMBDA_FUNCTIONS = ["HomeSecurity_ProcessImage", "HomeSecurity_ManageFaces"]
IAM_ROLE_NAME = "HomeSecurityLambdaRole"

def delete_s3_bucket():
    s3 = boto3.resource('s3', region_name=AWS_REGION)
    bucket = s3.Bucket(S3_BUCKET_NAME)
    
    print(f"--- Deleting S3 Bucket: {S3_BUCKET_NAME} ---")
    try:
        # Check if bucket exists
        s3.meta.client.head_bucket(Bucket=S3_BUCKET_NAME)
        
        # Delete all objects first
        print("ℹ️ Emptying bucket...")
        bucket.objects.all().delete()
        
        # Delete bucket
        bucket.delete()
        print(f"✅ Deleted bucket: {S3_BUCKET_NAME}")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print("ℹ️ Bucket does not exist.")
        else:
            print(f"❌ Error deleting bucket: {e}")

def delete_rekognition_collection():
    rekognition = boto3.client("rekognition", region_name=AWS_REGION)
    print(f"\n--- Deleting Rekognition Collection: {REKOGNITION_COLLECTION_ID} ---")
    
    try:
        rekognition.delete_collection(CollectionId=REKOGNITION_COLLECTION_ID)
        print(f"✅ Deleted collection: {REKOGNITION_COLLECTION_ID}")
    except ClientError as e:
         if e.response['Error']['Code'] == 'ResourceNotFoundException':
             print("ℹ️ Collection does not exist.")
         else:
             print(f"❌ Error deleting collection: {e}")

def delete_lambdas():
    lambda_client = boto3.client("lambda", region_name=AWS_REGION)
    print(f"\n--- Deleting Lambda Functions ---")
    
    for func in LAMBDA_FUNCTIONS:
        try:
            lambda_client.delete_function(FunctionName=func)
            print(f"✅ Deleted function: {func}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"ℹ️ Function {func} does not exist.")
            else:
                print(f"❌ Error deleting function {func}: {e}")

def delete_iam_role():
    iam = boto3.client("iam", region_name=AWS_REGION)
    print(f"\n--- Deleting IAM Role: {IAM_ROLE_NAME} ---")
    
    try:
        # Detach policies first
        attached_policies = iam.list_attached_role_policies(RoleName=IAM_ROLE_NAME)
        for policy in attached_policies['AttachedPolicies']:
            iam.detach_role_policy(RoleName=IAM_ROLE_NAME, PolicyArn=policy['PolicyArn'])
            print(f"ℹ️ Detached policy: {policy['PolicyName']}")
            
        # Delete Inline Policies if any (AWSLambdaBasicExecutionRole adds one sometimes)
        
        iam.delete_role(RoleName=IAM_ROLE_NAME)
        print(f"✅ Deleted role: {IAM_ROLE_NAME}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print("ℹ️ Role does not exist.")
        else:
            print(f"❌ Error deleting role: {e}")

if __name__ == "__main__":
    print(f"⚠️  WARNING: This will DELETE all AWS resources for project.")
    print(f"Region: {AWS_REGION}")
    confirm = input("Are you sure? (type 'yes' to proceed): ")
    
    if confirm.lower() == 'yes':
        delete_lambdas()
        delete_s3_bucket()
        delete_rekognition_collection()
        delete_iam_role()
        print("\n✨ Cleanup Complete!")
    else:
        print("Cancelled.")
