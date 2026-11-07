"""
Dukaanly Render 1-Click Deployment Automation Script
Uses the official Render REST API to create and launch the Dukaanly Blueprint.
"""
import sys
import os
import httpx
import json

def deploy_to_render(api_key: str):
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    print("==> Verifying Render API credentials...")
    with httpx.Client(timeout=15.0) as client:
        # 1. Fetch user / owner ID
        resp = client.get("https://api.render.com/v1/owners", headers=headers)
        if resp.status_code != 200:
            print(f"[ERROR] Failed to authenticate with Render API: {resp.status_code} - {resp.text}")
            return False
            
        owners = resp.json()
        if not owners:
            print("[ERROR] No workspace/owner found in your Render account.")
            return False
            
        owner = owners[0].get("owner", {})
        owner_id = owner.get("id")
        owner_name = owner.get("name") or owner.get("email")
        print(f"[OK] Authenticated as: {owner_name} (Owner ID: {owner_id})")
        
        # 2. Check existing blueprints
        blueprints_resp = client.get("https://api.render.com/v1/blueprints", headers=headers)
        existing_blueprint = None
        if blueprints_resp.status_code == 200:
            for bp in blueprints_resp.json():
                blueprint_data = bp.get("blueprint", {})
                if "dukaanly" in (blueprint_data.get("name") or "").lower():
                    existing_blueprint = blueprint_data
                    break
                    
        if existing_blueprint:
            bp_id = existing_blueprint.get("id")
            print(f"[INFO] Dukaanly Blueprint already exists: {bp_id}. Triggering sync...")
            sync_resp = client.post(f"https://api.render.com/v1/blueprints/{bp_id}/sync", headers=headers)
            if sync_resp.status_code in (200, 201, 202):
                print(f"[SUCCESS] Blueprint sync triggered! Services are deploying.")
                return True
            else:
                print(f"[WARN] Sync failed: {sync_resp.status_code} - {sync_resp.text}")

        # 3. Create new Blueprint instance
        print("==> Launching Dukaanly Blueprint on Render...")
        payload = {
            "name": "dukaanly",
            "repo": "https://github.com/sagarraj0570/dukaanly",
            "branch": "master",
            "ownerId": owner_id,
            "autoDeploy": True
        }
        create_resp = client.post("https://api.render.com/v1/blueprints", headers=headers, json=payload)
        if create_resp.status_code in (200, 201, 202):
            result = create_resp.json()
            print("[SUCCESS] Dukaanly Blueprint created successfully!")
            print(json.dumps(result, indent=2))
            return True
        else:
            print(f"[ERROR] Failed to create blueprint: {create_resp.status_code} - {create_resp.text}")
            return False

if __name__ == "__main__":
    api_key = sys.argv[1] if len(sys.argv) > 1 else os.getenv("RENDER_API_KEY")
    if not api_key:
        print("Usage: python scripts/deploy_render.py <RENDER_API_KEY>")
        sys.exit(1)
    success = deploy_to_render(api_key)
    sys.exit(0 if success else 1)
