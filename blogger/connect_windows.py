"""One-time owner-side Blogger OAuth connection. Never prints or commits tokens."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import AuthorizedSession, Request

REPO = "gamingpoddagames/-slnews247"
HOME = "https://slnews247live.blogspot.com/"
SCOPE = "https://www.googleapis.com/auth/blogger"

def gh(*args, value=None):
    return subprocess.run(["gh", *args], input=value, text=True, check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("client_json", type=Path)
    parser.add_argument("--enable", action="store_true", help="Enable automatic news publishing and label sync")
    args = parser.parse_args()
    if not shutil.which("gh"):
        raise SystemExit("Install GitHub CLI and run gh auth login first.")
    gh("auth", "status", "--hostname", "github.com")
    data = json.loads(args.client_json.read_text(encoding="utf-8"))
    client = data.get("installed")
    if not client or not client.get("client_id") or not client.get("client_secret"):
        raise SystemExit("Select a Google Desktop app OAuth client JSON, not Web or service account credentials.")
    flow = InstalledAppFlow.from_client_config(data, [SCOPE])
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent", authorization_prompt_message="Open the Google sign-in window to approve Blogger access.")
    if not credentials.refresh_token:
        raise SystemExit("No refresh token returned. No GitHub secrets changed.")
    credentials.refresh(Request())
    with AuthorizedSession(credentials) as session:
        response = session.get("https://www.googleapis.com/blogger/v3/users/self/blogs", params={"role":"ADMIN","fetchUserInfo":"true"},timeout=30)
        if response.status_code != 200:
            raise SystemExit("Blogger access check failed: HTTP "+str(response.status_code))
        blogs = response.json().get("items",[])
        match = next((b for b in blogs if urlsplit(b.get("url","")).hostname == urlsplit(HOME).hostname and "slnews" in "".join(c for c in b.get("name","").lower() if c.isalnum())),None)
        if not match:
            print("Authorized Blogger sites:")
            for b in blogs:
                print(b.get("name",""),b.get("url",""))
            raise SystemExit("Expected SL NEWS blog was not found. No GitHub secrets changed. Confirm the correct blog URL/account.")
        response = session.get("https://www.googleapis.com/blogger/v3/blogs/"+str(match["id"])+"/posts",params={"view":"ADMIN","maxResults":1,"fetchBodies":"false"},timeout=30)
        if response.status_code != 200:
            raise SystemExit("Blogger post access check failed: HTTP "+str(response.status_code))
    for name, val in (("BLOGGER_CLIENT_ID",client["client_id"]),("BLOGGER_CLIENT_SECRET",client["client_secret"]),("BLOGGER_REFRESH_TOKEN",credentials.refresh_token)):
        gh("secret","set",name,"--repo",REPO,value=val)
    gh("variable","set","SLNEWS_BLOGGER_URL","--repo",REPO,"--body",HOME)
    if args.enable:
        for name in ("SLNEWS_BLOGGER_PUBLISH_ENABLED","SLNEWS_BLOGGER_CATEGORY_ENABLED"):
            gh("variable","set",name,"--repo",REPO,"--body","true")
        gh("workflow","run","blogger-mirror.yml","--repo",REPO)
        print("Publishing requested. Check GitHub Actions for actual Blogger receipts.")
    else:
        print("Connection verified. Run again with --enable to activate publishing.")
    print("Verified target:", match["url"], "GitHub encrypted secrets saved.")

if __name__ == "__main__":
    main()
