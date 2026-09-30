#!/usr/bin/env python3
"""
Member Count V2 Report

Accurately counts members by:
1. Loading repgroups.dat to map Stripe product/plan IDs to target membership categories:
   - FreeMember
   - GroupMember
   - HobbyistMembership
   - ProDuoMember
   (Ignoring any subscription not mapped to one of these 4 groups)
2. Classifying subscriptions into Paid vs Free:
   - FreeMember product codes = Free
   - GroupMember, HobbyistMembership, ProDuoMember = Paid
   - 100% off / Exempt coupons = Overridden to Free
3. Parsing Stripe metadata (e.g., 'names', 'emails') for individual seat counts.
   - Defaults ProDuoMember to 2 seats if no metadata list is present.
"""

import os
import re
import sys
import stripe
from datetime import datetime

TARGET_GROUPS = {
    'FreeMember',
    'GroupMember',
    'HobbyistMembership',
    'ProDuoMember'
}

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
    
    # Fallback dictionary for testing/dev environments if repgroups.dat does not exist
    if not group_map:
        group_map = {
            'prod_BTnuDfBb21OmlD': 'FreeMember',
            'prod_BU3Ch9zQ5Pd4y2': 'FreeMember',
            'prod_BTw3Xdd5XzktCM': 'FreeMember',
            'prod_BUXofmSHI9wymZ': 'GroupMember',
            'hobbyist': 'HobbyistMembership',
            'pro': 'HobbyistMembership',
            'produo': 'ProDuoMember'
        }
    return group_map

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
    return False, None

def count_seats(s, group_name):
    metadata = s.get('metadata') or {}
    for key in ['names', 'emails', 'members', 'users']:
        val = metadata.get(key)
        if val and isinstance(val, str) and val.strip():
            items = [item.strip() for item in re.split(r'[,;\n]', val) if item.strip()]
            if items:
                return len(items)
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

    counts = {}
    for g in TARGET_GROUPS:
        counts[g] = {'paid_seats': 0, 'free_seats': 0, 'sub_count': 0, 'coupons': {}}

    processed_subs = set()
    total_processed = 0

    for s in stripe.Subscription.auto_paging_iter():
        if s['id'] in processed_subs:
            continue
        processed_subs.add(s['id'])

        status = s.get('status')
        canceled_at = s.get('canceled_at')
        ended_at = s.get('ended_at')
        if canceled_at is not None or ended_at is not None or status not in ['active', 'trialing']:
            continue

        plan = s.get('plan') or {}
        plan_id = plan.get('id', '')
        product_id = plan.get('product', '')

        group_name = repgroups.get(product_id) or repgroups.get(plan_id)

        if not group_name or group_name not in TARGET_GROUPS:
            continue

        total_processed += 1
        seats = count_seats(s, group_name)
        is_free_coupon, coupon_name = get_coupon_info(s)

        is_free = (group_name == 'FreeMember') or is_free_coupon

        group_data = counts[group_name]
        group_data['sub_count'] += 1

        if is_free:
            group_data['free_seats'] += seats
            c_key = coupon_name if coupon_name else ("Free Product" if group_name == 'FreeMember' else "Other Free")
            group_data['coupons'][c_key] = group_data['coupons'].get(c_key, 0) + seats
        else:
            group_data['paid_seats'] += seats

    print("HTML:\n</pre>")
    print("<div style='font-family: Arial, sans-serif; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>")
    print("<h2 style='color: #333; margin-top: 0;'>Member Count V2 Report (Product & Metadata Aware)</h2>")
    print(f"<p class='text-muted'>Processed {total_processed} active membership subscriptions.</p>")

    grand_paid = 0
    grand_free = 0
    grand_all = 0

    print("<table class='table table-bordered table-striped mt-3'>")
    print("<thead class='thead-dark'><tr><th>Group / Product Type</th><th class='text-right'>Paid Seats</th><th class='text-right'>Free Seats</th><th class='text-right'>Total Seats</th><th class='text-right'>Subscriptions</th></tr></thead>")
    print("<tbody>")

    for g in sorted(counts.keys()):
        d = counts[g]
        paid = d['paid_seats']
        free = d['free_seats']
        tot = paid + free
        subs_cnt = d['sub_count']

        grand_paid += paid
        grand_free += free
        grand_all += tot

        print(f"<tr><td><strong>{g}</strong></td><td class='text-right'>{paid}</td><td class='text-right'>{free}</td><td class='text-right'><strong>{tot}</strong></td><td class='text-right'>{subs_cnt}</td></tr>")

        if d['coupons']:
            for c_name, c_seats in sorted(d['coupons'].items()):
                print(f"<tr class='text-muted'><td style='padding-left: 30px;' colspan='2'>&bull; {c_name}</td><td class='text-right'>{c_seats}</td><td colspan='2'></td></tr>")

    print("<tr class='table-info' style='font-size: 1.1em;'>")
    print(f"<td><strong>Grand Total</strong></td><td class='text-right'><strong>{grand_paid}</strong></td><td class='text-right'><strong>{grand_free}</strong></td><td class='text-right'><strong>{grand_all}</strong></td><td></td>")
    print("</tr>")
    print("</tbody></table>")
    print("</div>\n<pre>")

    sys.exit(0)

if __name__ == '__main__':
    main()
