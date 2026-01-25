#!/usr/bin/env python3
import json
import requests
import time
import os

GITHUB_API_BASE = "https://api.github.com/repos/manuninkirill-bot/goldantelopeasia/contents/restaurants_all"
RAW_BASE = "https://raw.githubusercontent.com/manuninkirill-bot/goldantelopeasia/main/restaurants_all"

CITY_MAPPING = {
    "restaurants_cam_ranh": "Камрань",
    "restaurants_da_lat": "Далат",
    "restaurants_danang": "Дананг",
    "restaurants_hanoi": "Ханой",
    "restaurants_phu_quoc": "Фукуок",
    "restaurants_saigon": "Хошимин",
    "restaurants_nhatrang": "Нячанг",
    "restaurants_hoi_an": "Хойан",
    "restaurants_mui_ne": "Муйне",
    "restaurants_vung_tau": "Вунгтау",
    "restaurants_phan_thiet": "Фантьет"
}

def safe_request(url, retries=3, delay=2):
    """Make request with retries and delays"""
    for i in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                return resp
            elif resp.status_code == 403:
                print(f"  Rate limited, waiting {delay * (i+1)}s...")
                time.sleep(delay * (i+1))
            else:
                return None
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(delay)
    return None

def get_city_folders():
    """Get list of city folders from GitHub"""
    resp = safe_request(GITHUB_API_BASE)
    if not resp:
        return []
    
    data = resp.json()
    cities = []
    for item in data:
        if item["type"] == "dir" and item["name"].startswith("restaurants_"):
            cities.append(item["name"])
    return cities

def get_restaurants_in_city(city_folder):
    """Get list of restaurant folders in a city"""
    url = f"{GITHUB_API_BASE}/{city_folder}"
    resp = safe_request(url)
    if not resp:
        return []
    
    data = resp.json()
    restaurants = []
    for item in data:
        if item["type"] == "dir":
            restaurants.append(item["name"])
    return restaurants

def download_description_raw(city_folder, restaurant_folder):
    """Download description directly from raw.githubusercontent.com (no API limit)"""
    url = f"{RAW_BASE}/{city_folder}/{restaurant_folder}/description_ru.txt"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        
        content = resp.text
        
        result = {
            "name": restaurant_folder.replace("_", " "),
            "description": "",
            "cuisine_type": "",
            "review": "",
            "google_maps": ""
        }
        
        lines = content.strip().split("\n")
        if lines:
            result["name"] = lines[0].strip()
        
        for line in lines:
            if line.startswith("Описание:"):
                result["description"] = line.replace("Описание:", "").strip()
            elif line.startswith("Тип кухни:"):
                result["cuisine_type"] = line.replace("Тип кухни:", "").strip()
            elif line.startswith("Отзыв:"):
                result["review"] = line.replace("Отзыв:", "").strip()
            elif line.startswith("Google Maps:"):
                result["google_maps"] = line.replace("Google Maps:", "").strip()
        
        return result
    except:
        return None

def get_photo_urls_raw(city_folder, restaurant_folder):
    """Generate photo URLs (1-4 photos typical)"""
    photos = []
    for i in range(1, 5):
        url = f"{RAW_BASE}/{city_folder}/{restaurant_folder}/photo_{i}.jpg"
        photos.append(url)
    return photos

def import_all_restaurants():
    """Main function to import all restaurants"""
    print("Starting restaurant import v2 (with delays)...")
    
    all_restaurants = []
    
    city_folders = get_city_folders()
    print(f"Found {len(city_folders)} city folders: {city_folders}")
    
    for city_folder in city_folders:
        city_name = CITY_MAPPING.get(city_folder, city_folder.replace("restaurants_", "").replace("_", " ").title())
        print(f"\n=== Processing {city_name} ({city_folder}) ===")
        
        time.sleep(1)
        
        restaurants = get_restaurants_in_city(city_folder)
        print(f"Found {len(restaurants)} restaurants")
        
        for idx, restaurant_folder in enumerate(restaurants):
            time.sleep(0.3)
            
            desc = download_description_raw(city_folder, restaurant_folder)
            if not desc:
                continue
            
            photos = get_photo_urls_raw(city_folder, restaurant_folder)
            
            restaurant_id = f"vietnam_food_github_{city_folder}_{restaurant_folder}".lower().replace(" ", "_")
            
            restaurant = {
                "id": restaurant_id,
                "category": "restaurants",
                "title": desc["name"],
                "text": desc["description"],
                "cuisine_type": desc["cuisine_type"],
                "review": desc["review"],
                "google_maps": desc["google_maps"],
                "city": city_name,
                "country": "vietnam",
                "photos": photos,
                "source": "github_import",
                "date": "2026-01-19"
            }
            
            all_restaurants.append(restaurant)
            
            if (idx + 1) % 10 == 0:
                print(f"  Progress: {idx+1}/{len(restaurants)}")
        
        print(f"  Completed {city_name}: {len([r for r in all_restaurants if r['city'] == city_name])} restaurants")
    
    print(f"\n\nTotal restaurants fetched: {len(all_restaurants)}")
    
    listings_file = "listings_vietnam.json"
    if os.path.exists(listings_file):
        with open(listings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    
    if "restaurants" not in data:
        data["restaurants"] = []
    
    existing_ids = {r.get("id") for r in data["restaurants"]}
    
    added = 0
    for r in all_restaurants:
        if r["id"] not in existing_ids:
            data["restaurants"].append(r)
            added += 1
    
    with open(listings_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nAdded {added} NEW restaurants to {listings_file}")
    print(f"Total restaurants in file: {len(data['restaurants'])}")
    
    return all_restaurants

if __name__ == "__main__":
    import_all_restaurants()
