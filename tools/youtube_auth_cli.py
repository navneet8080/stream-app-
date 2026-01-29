#!/usr/bin/env python3
"""
YouTube OAuth CLI Tool
======================
Standalone CLI-only OAuth for YouTube Live API.

This tool must be run BEFORE Docker containers start.
It authenticates with YouTube and saves the token for the streaming engine.

Usage:
    python tools/youtube_auth_cli.py

Requirements:
    - secrets/client_secrets.json (Desktop OAuth credentials from Google Cloud Console)
    - Port 8080 must be available for OAuth callback
"""

import os
import sys
import json
from pathlib import Path

# Ensure we can find the secrets folder
BASE_DIR = Path(__file__).parent.parent
SECRETS_DIR = BASE_DIR / "secrets"
CLIENT_SECRETS_FILE = SECRETS_DIR / "client_secrets.json"
TOKEN_FILE = SECRETS_DIR / "token.json"

# YouTube Live API scope
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def validate_client_secrets():
    """Validate that client_secrets.json exists and is correct type."""
    if not CLIENT_SECRETS_FILE.exists():
        print("=" * 60)
        print("ERROR: client_secrets.json not found!")
        print("=" * 60)
        print(f"\nExpected location: {CLIENT_SECRETS_FILE}")
        print("\nTo fix this:")
        print("1. Go to Google Cloud Console")
        print("2. Navigate to APIs & Services > Credentials")
        print("3. Create OAuth 2.0 credentials as 'Desktop application'")
        print("4. Download the JSON file")
        print(f"5. Save it to: {SECRETS_DIR}/client_secrets.json")
        print("\n⚠️  IMPORTANT: Must be 'Desktop application', NOT 'Web application'")
        return False
    
    # Validate it's a Desktop app credential
    try:
        with open(CLIENT_SECRETS_FILE, "r") as f:
            creds_data = json.load(f)
        
        if "installed" in creds_data:
            print("✅ Client secrets validated: Desktop application type")
            return True
        elif "web" in creds_data:
            print("=" * 60)
            print("ERROR: Wrong OAuth credential type!")
            print("=" * 60)
            print("\nYour client_secrets.json is for 'Web application'")
            print("This tool requires 'Desktop application' credentials.")
            print("\nTo fix this:")
            print("1. Go to Google Cloud Console > Credentials")
            print("2. Create NEW OAuth credentials as 'Desktop application'")
            print("3. Download and replace client_secrets.json")
            return False
        else:
            print("ERROR: Invalid client_secrets.json format")
            return False
    except json.JSONDecodeError:
        print("ERROR: client_secrets.json is not valid JSON")
        return False


def authenticate():
    """Run OAuth flow and save token."""
    # Import here to fail fast if not installed
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("ERROR: Required packages not installed.")
        print("Run: pip install google-auth-oauthlib google-auth")
        return False
    
    print("\n" + "=" * 60)
    print("YouTube Live - OAuth Authentication")
    print("=" * 60)
    
    # Check for existing valid token
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if creds and creds.valid:
                print("\n✅ Existing token is still valid!")
                print(f"   Token file: {TOKEN_FILE}")
                return True
            elif creds and creds.expired and creds.refresh_token:
                print("\n🔄 Token expired, attempting refresh...")
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                # Save refreshed token
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
                print("✅ Token refreshed successfully!")
                return True
        except Exception as e:
            print(f"⚠️  Could not use existing token: {e}")
            print("   Will create new token...")
    
    # Create OAuth flow
    print("\n🌐 Starting OAuth flow...")
    print("   A browser window will open for Google login.")
    print("   Redirect URI: http://localhost:8080/")
    print()
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRETS_FILE),
            scopes=SCOPES
        )
        
        # Run local server for OAuth callback
        # CRITICAL: Must use port 8080 and exact redirect URI
        creds = flow.run_local_server(
            host="localhost",
            port=8080,
            prompt="consent",
            authorization_prompt_message="",
            success_message="Authentication successful! You can close this window.",
            open_browser=True
        )
        
        # Save the token
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        
        print("\n" + "=" * 60)
        print("✅ AUTHENTICATION SUCCESSFUL!")
        print("=" * 60)
        print(f"\nToken saved to: {TOKEN_FILE}")
        print("\nYou can now start the streaming engine.")
        print("The token will be automatically refreshed as needed.")
        return True
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ AUTHENTICATION FAILED!")
        print("=" * 60)
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure port 8080 is not in use")
        print("2. Verify client_secrets.json is 'Desktop application' type")
        print("3. Check that YouTube Data API v3 is enabled in Google Cloud Console")
        return False


def verify_token():
    """Verify the token works by making a test API call."""
    if not TOKEN_FILE.exists():
        print("❌ No token file found. Run authentication first.")
        return False
    
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        youtube = build("youtube", "v3", credentials=creds)
        
        # Test API call - get channel info
        request = youtube.channels().list(part="snippet", mine=True)
        response = request.execute()
        
        if response.get("items"):
            channel = response["items"][0]["snippet"]
            print("\n✅ Token verification successful!")
            print(f"   Connected to channel: {channel.get('title', 'Unknown')}")
            return True
        else:
            print("⚠️  Token valid but no channel found")
            return True
            
    except Exception as e:
        print(f"❌ Token verification failed: {e}")
        return False


def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("  YOUTUBE LIVE - CLI AUTHENTICATION TOOL")
    print("=" * 60)
    
    # Step 1: Validate client secrets
    if not validate_client_secrets():
        sys.exit(1)
    
    # Step 2: Authenticate
    if not authenticate():
        sys.exit(1)
    
    # Step 3: Verify token works
    print("\n🔍 Verifying token...")
    verify_token()
    
    print("\n" + "=" * 60)
    print("  SETUP COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Ensure videos are in the 'output/' folder")
    print("2. Run: docker compose up -d")
    print("3. Open dashboard: http://localhost:8000")
    print()


if __name__ == "__main__":
    main()
