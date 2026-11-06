"""
Stage 10 - Realistic Performance & Latency Benchmark Script
Measures min, p50, p95, p99, and max latency across core operations against live Dukaanly API.
"""

import asyncio
import time
import uuid
import statistics
import httpx
from decimal import Decimal

BASE_URL = "http://127.0.0.1:8000/api/v1"

def calc_stats(latencies: list[float]) -> dict:
    if not latencies:
        return {"count": 0, "min_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "max_ms": 0}
    lat_ms = [l * 1000.0 for l in latencies]
    lat_ms.sort()
    n = len(lat_ms)
    p50_idx = int(0.50 * n)
    p95_idx = min(int(0.95 * n), n - 1)
    p99_idx = min(int(0.99 * n), n - 1)
    return {
        "count": n,
        "min_ms": round(lat_ms[0], 2),
        "p50_ms": round(lat_ms[p50_idx], 2),
        "p95_ms": round(lat_ms[p95_idx], 2),
        "p99_ms": round(lat_ms[p99_idx], 2),
        "max_ms": round(lat_ms[-1], 2),
    }

async def run_benchmark():
    async with httpx.AsyncClient(timeout=10.0) as client:
        print("=== STAGE 10 OPERATIONAL PERFORMANCE BENCHMARK ===")
        print(f"Target: {BASE_URL}")

        # 1. Health & Readiness Check Latency (50 iterations)
        readiness_latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            r = await client.get(f"{BASE_URL}/health/ready")
            t1 = time.perf_counter()
            if r.status_code == 200:
                readiness_latencies.append(t1 - t0)
        stats_ready = calc_stats(readiness_latencies)
        print(f"\n1. Health Readiness Check (/health/ready):")
        print(f"   Count: {stats_ready['count']} | p50: {stats_ready['p50_ms']}ms | p95: {stats_ready['p95_ms']}ms | max: {stats_ready['max_ms']}ms")

        # 2. Setup user and get token
        user_email = f"bench_user_{uuid.uuid4().hex[:8]}@example.com"
        reg_res = await client.post(f"{BASE_URL}/auth/register", json={
            "name": "Benchmark User",
            "email": user_email,
            "password": "BenchmarkPassword123!",
            "role": "customer"
        })
        login_res = await client.post(f"{BASE_URL}/auth/login", json={
            "email": user_email,
            "password": "BenchmarkPassword123!"
        })
        cust_token = login_res.json()["access_token"]
        cust_headers = {"Authorization": f"Bearer {cust_token}"}

        # 3. PostGIS Geospatial Shop Discovery (50 iterations)
        discovery_latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            r = await client.get(
                f"{BASE_URL}/shops",
                params={"latitude": 25.6125, "longitude": 85.1405, "radius_meters": 5000, "verified_only": True},
                headers=cust_headers
            )
            t1 = time.perf_counter()
            if r.status_code == 200:
                discovery_latencies.append(t1 - t0)
        stats_disc = calc_stats(discovery_latencies)
        print(f"\n2. PostGIS Shop Discovery (/shops?latitude=...&verified_only=true):")
        print(f"   Count: {stats_disc['count']} | p50: {stats_disc['p50_ms']}ms | p95: {stats_disc['p95_ms']}ms | max: {stats_disc['max_ms']}ms")

        # Login as demo shop owner to ensure we have an orderable shop with inventory
        owner_login = await client.post(f"{BASE_URL}/auth/login", json={
            "email": "shop@dukaanly.com",
            "password": "Password123!"
        })
        owner_token = owner_login.json()["access_token"]
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        # Check or create benchmark shop
        bench_shop_res = await client.post(f"{BASE_URL}/shops", json={
            "name": "Benchmark Super Store",
            "address": "Boring Canal Road, Patna",
            "location": {"latitude": 25.6125, "longitude": 85.1405}
        }, headers=owner_headers)
        if bench_shop_res.status_code == 201:
            shop_id = bench_shop_res.json()["id"]
        else:
            # Get owner's first shop
            owner_shops_res = await client.get(
                f"{BASE_URL}/shops",
                params={"latitude": 25.6125, "longitude": 85.1405, "radius_meters": 5000, "verified_only": True},
                headers=cust_headers
            )
            shop_id = owner_shops_res.json()["items"][0]["id"]

        # Create benchmark product with 100 stock
        bench_prod_res = await client.post(f"{BASE_URL}/shops/{shop_id}/products", json={
            "name": f"Benchmark Basmati Rice {uuid.uuid4().hex[:6]}",
            "price": 120.00
        }, headers=owner_headers)
        target_product_id = bench_prod_res.json()["id"]

        # Ensure inventory is 100
        await client.patch(
            f"{BASE_URL}/products/{target_product_id}/inventory",
            json={"stock": 100, "expected_version": 1},
            headers=owner_headers
        )

        print(f"   Benchmark Shop ID: {shop_id} | Product ID: {target_product_id} (Stock: 100)")

        # 4. Product Catalog Fetch Latency (50 iterations)
        catalog_latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            r = await client.get(f"{BASE_URL}/shops/{shop_id}/products", headers=cust_headers)
            t1 = time.perf_counter()
            if r.status_code == 200:
                catalog_latencies.append(t1 - t0)
        stats_cat = calc_stats(catalog_latencies)
        print(f"\n3. Shop Product Catalog Listing (/shops/{{shop_id}}/products):")
        print(f"   Count: {stats_cat['count']} | p50: {stats_cat['p50_ms']}ms | p95: {stats_cat['p95_ms']}ms | max: {stats_cat['max_ms']}ms")

        # 5. Full Checkout & Reservation Latency (20 consecutive checkouts)
        checkout_latencies = []
        created_orders = []
        if target_product_id:
            for i in range(20):
                # Add 1 item to cart
                c_res = await client.post(f"{BASE_URL}/cart/items", json={"product_id": target_product_id, "quantity": 1}, headers=cust_headers)
                if c_res.status_code != 200 and i == 0:
                    print(f"   [Cart add notice] status: {c_res.status_code}, detail: {c_res.text[:120]}")
                t0 = time.perf_counter()
                r = await client.post(
                    f"{BASE_URL}/orders/checkout",
                    json={"idempotency_key": str(uuid.uuid4()), "destination_latitude": 25.6125, "destination_longitude": 85.1405},
                    headers=cust_headers
                )
                t1 = time.perf_counter()
                if r.status_code == 201:
                    checkout_latencies.append(t1 - t0)
                    created_orders.append(r.json()["id"])
                elif i == 0:
                    print(f"   [Checkout notice] status: {r.status_code}, detail: {r.text[:120]}")
        stats_checkout = calc_stats(checkout_latencies)
        print(f"\n4. Transactional Checkout & Inventory Reservation (/orders/checkout):")
        print(f"   Count: {stats_checkout['count']} | p50: {stats_checkout['p50_ms']}ms | p95: {stats_checkout['p95_ms']}ms | max: {stats_checkout['max_ms']}ms")

        # 6. Payment Initiation & Verification Latency
        from app.services.payment_provider import compute_mock_razorpay_signature
        payment_verify_latencies = []
        for ord_id in created_orders[:15]:
            init_res = await client.post(f"{BASE_URL}/orders/{ord_id}/payment", headers=cust_headers)
            if init_res.status_code == 200:
                rzp_order_id = init_res.json()["provider_order_id"]
                fake_pay_id = f"pay_{uuid.uuid4().hex[:14]}"
                mock_sig = compute_mock_razorpay_signature(rzp_order_id, fake_pay_id)
                t0 = time.perf_counter()
                v_res = await client.post(
                    f"{BASE_URL}/payments/verify",
                    json={"razorpay_order_id": rzp_order_id, "razorpay_payment_id": fake_pay_id, "razorpay_signature": mock_sig},
                    headers=cust_headers
                )
                t1 = time.perf_counter()
                if v_res.status_code == 200:
                    payment_verify_latencies.append(t1 - t0)
        stats_pay = calc_stats(payment_verify_latencies)
        print(f"\n5. Payment Cryptographic Verification (/payments/verify):")
        print(f"   Count: {stats_pay['count']} | p50: {stats_pay['p50_ms']}ms | p95: {stats_pay['p95_ms']}ms | max: {stats_pay['max_ms']}ms")

        # 6. Delivery Tracking & Smart ETA Latency
        delivery_latencies = []
        if created_orders:
            target_ord = created_orders[0]
            deliv_create = await client.post(
                f"{BASE_URL}/deliveries",
                json={"order_id": target_ord, "destination_latitude": 25.6125, "destination_longitude": 85.1405},
                headers=owner_headers
            )
            deliv_id = deliv_create.json().get("id") if deliv_create.status_code == 201 else None
            if deliv_id:
                for _ in range(30):
                    t0 = time.perf_counter()
                    d_res = await client.get(f"{BASE_URL}/deliveries/{deliv_id}/eta", headers=cust_headers)
                    t1 = time.perf_counter()
                    if d_res.status_code == 200:
                        delivery_latencies.append(t1 - t0)
        stats_deliv = calc_stats(delivery_latencies)
        print(f"\n6. Delivery Smart ETA Tracking (/deliveries/{{id}}/eta):")
        print(f"   Count: {stats_deliv['count']} | p50: {stats_deliv['p50_ms']}ms | p95: {stats_deliv['p95_ms']}ms | max: {stats_deliv['max_ms']}ms")

        print("\n=== BENCHMARK COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
