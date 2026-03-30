import boto3
import json
import os
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# Load Config
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "nghi-face-recognition-bucket")
REKOGNITION_COLLECTION_ID = os.getenv("REKOGNITION_COLLECTION_ID", "home-security-faces")

def setup_s3():
    s3 = boto3.client("s3", region_name=AWS_REGION)
    
    print(f"--- Setting up S3 Bucket: {S3_BUCKET_NAME} ---")
        
    # 1. Create Bucket
    try:
        if AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=S3_BUCKET_NAME)
        else:
            s3.create_bucket(
                Bucket=S3_BUCKET_NAME,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION}
            )
        print(f"✅ Created bucket: {S3_BUCKET_NAME}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
            print(f"ℹ️ Bucket already exists and is owned by you.")
        elif e.response['Error']['Code'] == 'BucketAlreadyExists':
            print(f"❌ Bucket name '{S3_BUCKET_NAME}' is taken. Please choose another name in .env")
            return
        else:
            print(f"❌ Error creating bucket: {e}")
            return

    # 2. Disable Block Public Access (to allow public read policy)
    try:
        s3.put_public_access_block(
            Bucket=S3_BUCKET_NAME,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': False,
                'IgnorePublicAcls': False,
                'BlockPublicPolicy': False,
                'RestrictPublicBuckets': False
            }
        )
        print("✅ Disabled 'Block Public Access'")
    except ClientError as e:
        print(f"❌ Error disabling block public access: {e}")

    # 3. Apply Bucket Policy (Public Read)
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{S3_BUCKET_NAME}/*"
            }
        ]
    }
    
    try:
        s3.put_bucket_policy(Bucket=S3_BUCKET_NAME, Policy=json.dumps(bucket_policy))
        print("✅ Applied Public Read policy")
    except ClientError as e:
        print(f"❌ Error applying bucket policy: {e}")

    # 4. Apply CORS Configuration (for Web Uploads)
    cors_configuration = {
        'CORSRules': [{
            'AllowedHeaders': ['*'],
            'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE', 'HEAD'],
            'AllowedOrigins': ['*'], # Allow localhost and Vercel
            'ExposeHeaders': ['ETag']
        }]
    }

    try:
        s3.put_bucket_cors(Bucket=S3_BUCKET_NAME, CORSConfiguration=cors_configuration)
        print("✅ Applied CORS configuration")
    except ClientError as e:
        print(f"❌ Error applying CORS: {e}")

def setup_rekognition():
    rekognition = boto3.client("rekognition", region_name=AWS_REGION)
    print(f"\n--- Setting up Rekognition Collection: {REKOGNITION_COLLECTION_ID} ---")
    
    try:
        rekognition.create_collection(CollectionId=REKOGNITION_COLLECTION_ID)
        print(f"✅ Created collection: {REKOGNITION_COLLECTION_ID}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
            print(f"ℹ️ Collection already exists.")
        else:
            print(f"❌ Error creating collection: {e}")

if __name__ == "__main__":
    from botocore.exceptions import NoCredentialsError, PartialCredentialsError

    print("🔄 Attempting to connect using AWS CLI credentials (SSO/Profile)...")
    try:
        # Check if we can make a call
        sts = boto3.client("sts", region_name=AWS_REGION)
        identity = sts.get_caller_identity()
        print(f"✅ Authenticated as: {identity['Arn']}")
        
        setup_s3()
        setup_rekognition()
        print("\n🎉 AWS Infrastructure Setup Complete!")
        
    except (NoCredentialsError, PartialCredentialsError):
        print("\n❌ No valid AWS credentials found.")
        print("💡 Tip: If using AWS SSO, run: 'aws sso login --profile <your-profile>'")
        print("   Or configure with: 'aws configure sso'")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
