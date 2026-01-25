#!/usr/bin/env python3
import json
import requests
import time
import re
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
    "restaurants_nha_trang": "Нячанг",
    "restaurants_hoi_an": "Хойан",
    "restaurants_mui_ne": "Муйне",
    "restaurants_vung_tau": "Вунгтау"
}

def get_city_folders():
    """Get list of city folders from GitHub"""
    resp = requests.get(GITHUB_API_BASE)
    if resp.status_code != 200:
        print(f"Error fetching city folders: {resp.status_code}")
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
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Error fetching restaurants in {city_folder}: {resp.status_code}")
        return []
    
    data = resp.json()
    restaurants = []
    for item in data:
        if item["type"] == "dir":
            restaurants.append(item["name"])
    return restaurants

def get_restaurant_files(city_folder, restaurant_folder):
    """Get list of files in a restaurant folder"""
    url = f"{GITHUB_API_BASE}/{city_folder}/{restaurant_folder}"
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Error fetching files for {restaurant_folder}: {resp.status_code}")
        return []
    
    return resp.json()

def download_description(city_folder, restaurant_folder):
    """Download and parse description_ru.txt"""
    url = f"{RAW_BASE}/{city_folder}/{restaurant_folder}/description_ru.txt"
    resp = requests.get(url)
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

def get_photo_urls(city_folder, restaurant_folder, files):
    """Get URLs for restaurant photos"""
    photos = []
    for f in files:
        if f["name"].startswith("photo_") and f["name"].endswith(".jpg"):
            photos.append(f["download_url"])
    return photos

def import_all_restaurants():
    """Main function to import all restaurants"""
    print("Starting restaurant import from GitHub...")
    
    all_restaurants = []
    
    city_folders = get_city_folders()
    print(f"Found {len(city_folders)} city folders: {city_folders}")
    
    for city_folder in city_folders:
        city_name = CITY_MAPPING.get(city_folder, city_folder.replace("restaurants_", "").replace("_", " ").title())
        print(f"\nProcessing {city_name} ({city_folder})...")
        
        restaurants = get_restaurants_in_city(city_folder)
        print(f"  Found {len(restaurants)} restaurants")
        
        for restaurant_folder in restaurants:
            time.sleep(0.2)
            
            files = get_restaurant_files(city_folder, restaurant_folder)
            if not files:
                continue
            
            desc = download_description(city_folder, restaurant_folder)
            if not desc:
                continue
            
            photos = get_photo_urls(city_folder, restaurant_folder, files)
            
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
            print(f"    + {desc['name']} ({len(photos)} photos)")
    
    print(f"\n\nTotal restaurants imported: {len(all_restaurants)}")
    
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
    
    print(f"\nAdded {added} new restaurants to {listings_file}")
    print(f"Total restaurants in file: {len(data['restaurants'])}")
    
    return all_restaurants

if __name__ == "__main__":
    import_all_restaurants()
