#!/usr/bin/python3

TOKEN = ""
with open("eventbrite.token") as fd:
    TOKEN = fd.read().strip()
import requests
import csv,sys
from datetime import datetime, timedelta

def get_super_event_grid(super_map, oauth_token):
    headers = {"Authorization": f"Bearer {oauth_token}"}

    # 1. Setup 24-month Grid
    now = datetime.now()
    month_keys = []
    start_point = (now - timedelta(days=365)).replace(day=1)
    for i in range(25):
        m_key = (start_point + timedelta(days=i*31)).strftime('%Y-%m')
        if len(month_keys) < 24: month_keys.append(m_key)

    # Flatten IDs for the API search, but keep the super_grid for storage
    all_target_ids = [str(sid) for sublist in super_map.values() for sid in sublist]
    super_grid = {name: {m: {"s": 0, "c": 0} for m in month_keys} for name in super_map.keys()}

    # 2. Get Org ID
    org_res = requests.get("https://www.eventbriteapi.com/v3/users/me/organizations/", headers=headers)
    org_id = org_res.json()['organizations'][0]['id']

    # 3. Pull all events
    url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/"
    params = {"status": "live,ended,completed,started", "time_filter": "all", "expand": "ticket_classes", "page_size": 100}

    print(f"Rolling up {len(all_target_ids)} IDs into {len(super_map)} Super-Events...")
    has_more = True
    continuation = None
    while has_more:
        if continuation: params['continuation'] = continuation
        response = requests.get(url, headers=headers, params=params).json()

        for event in response.get('events', []):
            eid, pid = str(event.get('id')), str(event.get('primary_event_id') or event.get('series_id', "None"))

            # Find which Super-Event this specific date belongs to
            for super_name, id_list in super_map.items():
                if eid in id_list or pid in id_list:
                    m_key = event.get('start', {}).get('utc', '')[:7]
                    if m_key in super_grid[super_name]:
                        tcs = event.get('ticket_classes', [])
                        super_grid[super_name][m_key]["s"] += sum(t.get('quantity_sold', 0) for t in tcs)
                        super_grid[super_name][m_key]["c"] += event.get('capacity', 0) or sum(t.get('quantity_total', 0) for t in tcs)

        has_more = response.get('pagination', {}).get('has_more_items', False)
        continuation = response.get('pagination', {}).get('continuation')

    # 4. PRINTING
    short_months = [m[5:] + "-" + m[2:4] for m in month_keys]
    header = "Category".ljust(25) + "|" + "|".join(m.center(6) for m in short_months)
    print("\n" + header + "\n" + "-" * len(header))

    for name in super_map.keys():
        row = [name.ljust(25)]
        for m in month_keys:
            s, c = super_grid[name][m]['s'], super_grid[name][m]['c']
            row.append(f"{int(s/c*100)}%".center(6) if c > 0 else "-".center(6))
        print("|".join(row))
    # 4. CSV DUMP TO STDOUT
    print("\n\n--- BEGIN CSV DUMP ---\n\n")
    writer = csv.writer(sys.stdout)
    writer.writerow(["Category"] + month_keys)

    for name, months in super_grid.items():
        row = [name]
        for m in month_keys:
            s, c = months[m]['s'], months[m]['c']
            val = round(s / c, 2) if c > 0 else ""
            row.append(val)
        writer.writerow(row)
    print("--- END CSV DUMP ---")

# --- DEFINE YOUR GROUPS HERE ---
MY_MAPPINGS = {
    "Epilog": ["444283543037"], 
    "MOPA": ["1982595934811"], 
    "Wood Orientation": ["119567829597"],  
    "Wood Bandsaw": ["557157070797"],
    "Wood Lathe": ["1965258959451"],
    "Wood Serving": ["1612325150929"],
    "Blacksmithing": ["1243682861919"],
    "Waterjet": ["663602140867"],
    "Design Tools": ["632359854347", "850035929347", "850045999467","1320096898359"], #Inkscape, Bkebder, Onshape, Meetup
    "Pottery": ["678019884727", "1596586807119"], #Glazing, Intro
    "Metal Fab": ["1092937859559"], # VBandsaw
    "Soft Metals": ["1978809165482","1740582431909", "1968713594357"], # Siver Wire Scape,< Copper Pendant, Smith & Annel
    "Shopbot": ["1978640823968"],
    "Lil Tormy": ["1867525161029"],
    "Soldering": ["1703566807179"],
    "Auto": ["1981598624830"],
    "Welding": ["1982281184384","1982278329846"], # TIG, MIG
    "Machine Shop": ["1982282866415", "1982283357885"], # Lathe Mill
    "Glenn": ["1982227839829", "1982220233077"] # DriilDoctor, TOrmech
}

#get_super_event_grid(MY_MAPPINGS, TOKEN)
get_super_event_grid(MY_MAPPINGS, TOKEN)
