#!/usr/bin/env python3
import sqlite3
import os
import sys

def main():
    # Find database path relative to script location
    # Note: the script is run with cwd="authlibs/reports/reports/" so we can use relative path or resolve it
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../makeit.db'))
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}", file=sys.stderr)
        sys.exit(1)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Query members with active subscriptions.
    # We check:
    # 1. subscription.expires_date is in the future or within the 14-day grace period
    # 2. or subscription.active is 'true'
    query = """
        SELECT DISTINCT m.email, m.alt_email
        FROM members m
        JOIN subscriptions s ON s.member_id = m.id
        WHERE (
            (s.expires_date IS NOT NULL AND s.expires_date > datetime('now', '-14 days'))
            OR s.active = 'true'
        )
    """
    
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    # Output headers
    print("Group Email [Required],Member Email,Member Type,Member Role")
    
    group_email = "active@makeitlabs.com"
    member_type = "USER"
    member_role = "MEMBER"
    
    emails_seen = set()
    
    for email, alt_email in rows:
        for addr in (email, alt_email):
            if addr:
                addr_clean = addr.strip()
                if addr_clean and addr_clean not in emails_seen:
                    emails_seen.add(addr_clean)
                    print(f"{group_email},{addr_clean},{member_type},{member_role}")

if __name__ == "__main__":
    main()
