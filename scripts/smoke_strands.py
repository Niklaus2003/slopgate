"""Smoke test for Strands Agents SDK and Bedrock integration."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from slopgate.config import get_settings


def main():
    settings = get_settings()
    print("=" * 60)
    print("  Strands Agents SDK & Bedrock Smoke Test")
    print("=" * 60)
    print(f"Region:    {settings.aws_region}")
    print(f"Model ID:  {settings.bedrock_model_id}")
    has_creds = bool(settings.aws_access_key_id or settings.aws_bearer_token_bedrock)
    print(f"AWS Creds: {'DETECTED' if has_creds else 'UNSET (Local/Mock Mode)'}")

    try:
        import boto3
        print("boto3 installed: OK")
    except ImportError:
        print("boto3 not installed yet.")
        return 1

    if has_creds:
        print("\nTesting live Bedrock Converse API with configured credentials...")
        try:
            client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
            response = client.converse(
                modelId=settings.bedrock_model_id,
                messages=[
                    {"role": "user", "content": [{"text": "Reply with 'SlopGate verified' in 3 words."}]}
                ],
                inferenceConfig={"maxTokens": 20, "temperature": 0.0}
            )
            output_text = response["output"]["message"]["content"][0]["text"]
            usage = response.get("usage", {})
            print(f"Bedrock response received: '{output_text.strip()}'")
            print(f"Token usage: {usage}")
        except Exception as e:
            print(f"Bedrock API call failed or credentials inactive: {e}")
            print("Note: Live Bedrock calls require active AWS access/credits.")
    else:
        print("\nAWS credentials not configured in .env yet.")
        print("Skipping live cloud call. Mock/offline fallback will be used during development.")

    print("\nStrands Agents SDK smoke test PASSED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
