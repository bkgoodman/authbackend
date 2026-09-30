#!/usr/bin/env python3
"""
Member Count V2 Report

Accurately counts members by:
1. Loading repgroups.dat to map Stripe product/plan IDs to membership categories:
   - FreeMember (including FIRST robotics)
   - GroupMember
   - HobbyistMembership (or hobbyist)
   - ProMembership (or pro)
   - ProDuoMember (or produo)
2. Classifying subscriptions into Paid vs Free:
   - FreeMember product codes / FIRST robotics = Free
   - 100% off / Exempt coupons = Overridden to Free
   - Other membership plans = Paid
3. Parsing Stripe metadata (e.g., 'names', 'emails', 'students', 'count') for individual seat counts.
   - Defaults ProDuoMember to 2 seats if no metadata list is present.
4. Displaying a detailed breakdown by Group and Coupon type, plus an Ignored Subscriptions diagnostics section.
"""

import os
import re
import sys
import stripe
from datetime import datetime

EXEMPT_COUPONS = {
    '100PERCENTOFF',
    'NonProfit -Free 1yr Memberships',
    '100% off in perpetuity- Do NOT use',
    'LCpqqG55'
}

def load_repgroups():
    group_map = {}
    paths = [
        'repgroups.dat',
        '../repgroups.dat',
        '../../repgroups.dat',
        '/var/www/authbackend/repgroups.dat'
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split()
                            if len(parts) >= 2:
                                group_map[parts[0]] = parts[1]
                break
            except Exception as e:
                print(f"Warning: Error reading {p}: {e}", file=sys.stderr)
    
    # Standard plan ID fallbacks
    group_map['hobbyist'] = 'HobbyistMembership'
    group_map['pro'] = 'ProMembership'
    group_map['produo'] = 'ProDuoMember'

    return group_map

def normalize_group_name(raw_name):
    if not raw_name:
        return None
    name_lower = raw_name.lower().strip()
    if 'produo' in name_lower:
        return 'ProDuoMember'
    elif 'pro' in name_lower:
        return 'ProMembership'
    elif 'hobbyist' in name_lower:
        return 'HobbyistMembership'
    elif 'first' in name_lower or 'robotics' in name_lower:
        return 'FreeMember'
    elif 'free' in name_lower:
        return 'FreeMember'
    elif 'group' in name_lower:
        return 'GroupMember'
    return raw_name

def get_coupon_info(s):
    try:
        discount = s.get('discount')
        if discount and discount.get('coupon'):
            c = discount['coupon']
            c_name = c.get('name') or ''
            c_id = c.get('id') or ''
            pct = c.get('percent_off')
            is_100_pct = (pct == 100) or (c_name in EXEMPT_COUPONS) or (c_id in EXEMPT_COUPONS)
            coupon_label = c_name if c_name else c_id
            return is_100_pct, coupon_label
    except Exception:
        pass
    return False, "No Coupon"

def count_seats(s, group_name):
    metadata = s.get('metadata') or {}
    # Check list metadata fields
    for key in ['names', 'emails', 'members', 'users', 'students', 'members_list', 'team_members']:
        val = metadata.get(key)
        if val and isinstance(val, str) and val.strip():
            items = [item.strip() for item in re.split(r'[,;\n]', val) if item.strip()]
            if items:
                return len(items)
    # Check numeric metadata fields
    for key in ['count', 'seats', 'num_members', 'total_members', 'quantity']:
        val = metadata.get(key)
        if val:
            try:
                num = int(val)
                if num > 0:
                    return num
            except ValueError:
                pass
    if group_name == 'ProDuoMember':
        return 2
    return 1

def main():
    try:
        stripe.api_key = open("stripenamefix.key").readline().strip()
    except FileNotFoundError:
        key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../stripenamefix.key"))
        if os.path.exists(key_path):
            stripe.api_key = open(key_path).readline().strip()
        else:
            print("Error: stripenamefix.key not found.", file=sys.stderr)
            sys.exit(1)

    stripe.api_version = '2020-08-27'
    repgroups = load_repgroups()

    # Structure: counts[group_name][coupon_name] = {'paid': 0, 'free': 0, 'total': 0, 'subs': 0}
    counts = {}
    ignored_subs = []

    processed_subs = set()
    total_processed = 0

    for s in stripe.Subscription.auto_paging_iter():
        if s['id'] in processed_subs:
            continue
        processed_subs.add(s['id'])

        canceled_at = s.get('canceled_at')
        ended_at = s.get('ended_at')
        plan = s.get('plan') or {}
        plan_active = plan.get('active', True)

        # Active check aligned with original membercount script
        if canceled_at is not None or ended_at is not None or not plan_active:
            continue

        plan_id = plan.get('id', '')
        product_id = plan.get('product', '')

        raw_group = repgroups.get(product_id) or repgroups.get(plan_id)
        if not raw_group:
            raw_group = plan_id

        group_name = normalize_group_name(raw_group)
        is_free_coupon, coupon_name = get_coupon_info(s)

        # If not in standardized groups, but present in repgroups, treat as mapped group
        if not group_name and product_id in repgroups:
            group_name = repgroups[product_id]

        # If still unrecognized as a membership
        valid_groups = ['HobbyistMembership', 'ProMembership', 'ProDuoMember', 'FreeMember', 'GroupMember']
        if not group_name or (group_name not in valid_groups and raw_group not in repgroups.values()):
            ignored_subs.append({
                'id': s['id'],
                'product': product_id,
                'plan': plan_id,
                'coupon': coupon_name,
                'metadata': s.get('metadata') or {}
            })
            continue

        total_processed += 1
        seats = count_seats(s, group_name)
        is_free = (group_name == 'FreeMember') or is_free_coupon

        if group_name not in counts:
            counts[group_name] = {}

        if coupon_name not in counts[group_name]:
            counts[group_name][coupon_name] = {'paid': 0, 'free': 0, 'total': 0, 'subs': 0}

        entry = counts[group_name][coupon_name]
        entry['subs'] += 1
        entry['total'] += seats

        if is_free:
            entry['free'] += seats
        else:
            entry['paid'] += seats

    # Print HTML output
    print("HTML:\n</pre>")
    print("<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>")
    print("<h2 style='color: #333; margin-top: 0;'>Member Count V2 Report (Product & Metadata Aware)</h2>")
    print(f"<p class='text-muted'>Processed {total_processed} active membership subscriptions.</p>")

    grand_paid = 0
    grand_free = 0
    grand_all = 0
    grand_subs = 0

    print("<table class='table table-bordered mt-3'>")
    print("<thead class='thead-dark'><tr><th>Group / Coupon</th><th class='text-right'>Total Seats</th><th class='text-right'>Paid Seats</th><th class='text-right'>Free Seats</th><th class='text-right'>Subscriptions</th></tr></thead>")
    print("<tbody>")

    for g in sorted(counts.keys()):
        g_data = counts[g]
        g_paid = sum(c['paid'] for c in g_data.values())
        g_free = sum(c['free'] for c in g_data.values())
        g_tot = sum(c['total'] for c in g_data.values())
        g_subs = sum(c['subs'] for c in g_data.values())

        grand_paid += g_paid
        grand_free += g_free
        grand_all += g_tot
        grand_subs += g_subs

        # Group header row
        print(f"<tr class='table-secondary'><td colspan='5'><strong>{g}</strong> (Total Seats: {g_tot} | Paid: {g_paid} | Free: {g_free} | Subscriptions: {g_subs})</td></tr>")

        for coupon in sorted(g_data.keys()):
            c_info = g_data[coupon]
            print(f"<tr><td style='padding-left: 25px;'>{coupon}</td><td class='text-right'>{c_info['total']}</td><td class='text-right'>{c_info['paid']}</td><td class='text-right'>{c_info['free']}</td><td class='text-right'>{c_info['subs']}</td></tr>")

    print("<tr class='table-info' style='font-size: 1.1em;'>")
    print(f"<td><strong>Grand Total</strong></td><td class='text-right'><strong>{grand_all}</strong></td><td class='text-right'><strong>{grand_paid}</strong></td><td class='text-right'><strong>{grand_free}</strong></td><td class='text-right'><strong>{grand_subs}</strong></td>")
    print("</tr>")
    print("</tbody></table>")

    # Diagnostic section for Ignored Subscriptions if any exist
    if ignored_subs:
        print("<h4 class='mt-4 text-warning'>Ignored Active Subscriptions (Diagnostic Check)</h4>")
        print(f"<p class='text-muted'>Found {len(ignored_subs)} active subscriptions not recognized as standard memberships:</p>")
        print("<table class='table table-sm table-hover text-muted'>")
        print("<thead><tr><th>Sub ID</th><th>Product ID</th><th>Plan ID</th><th>Coupon</th><th>Metadata</th></tr></thead><tbody>")
        for ig in ignored_subs[:50]:  # Limit to 50 items
            meta_str = str(ig['metadata']) if ig['metadata'] else ''
            print(f"<tr><td><code>{ig['id']}</code></td><td><code>{ig['product']}</code></td><td><code>{ig['plan']}</code></td><td>{ig['coupon']}</td><td><small>{meta_str}</small></td></tr>")
        print("</tbody></table>")

    print("</div>\n<pre>")

    sys.exit(0)

if __name__ == '__main__':
    main()
