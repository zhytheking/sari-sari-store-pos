import bcrypt
import sqlite3
import os
from pathlib import Path

# Database path
db_path = Path(__file__).parent / "data" / "sari_sari_pos.db"

print("=" * 60)
print("  CASHIER ACCOUNT CREATOR")
print("=" * 60)

if not db_path.exists():
    print(f"❌ Database not found at {db_path}")
    print("Please run the application first to create the database.")
    exit(1)

# Connect to database
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    # Check if cashier exists first
    cursor.execute("SELECT id, username, full_name, role, is_active FROM users WHERE username = 'cashier'")
    existing = cursor.fetchone()
    
    if existing:
        print(f"\nℹ️ Cashier account already exists:")
        print(f"   ID: {existing[0]}")
        print(f"   Username: {existing[1]}")
        print(f"   Full Name: {existing[2]}")
        print(f"   Role: {existing[3]}")
        print(f"   Active: {existing[4]}")
        
        # Ask if user wants to reset password
        response = input("\nDo you want to reset the password? (yes/no): ").strip().lower()
        if response == 'yes' or response == 'y':
            # Delete and recreate
            cursor.execute("DELETE FROM users WHERE username = 'cashier'")
            print("   ✅ Old account deleted")
        else:
            print("   Skipping password reset")
            # Still verify password
            cursor.execute("SELECT password_hash FROM users WHERE username = 'cashier'")
            result = cursor.fetchone()
            if result:
                test_password = 'cashier123'
                if bcrypt.checkpw(test_password.encode('utf-8'), result[0].encode('utf-8')):
                    print("   ✅ Password verification: SUCCESS")
                else:
                    print("   ⚠️ Password verification: FAILED - Consider resetting")
            conn.close()
            exit(0)
    
    # Hash password
    password = 'cashier123'
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Insert cashier with correct role
    cursor.execute("""
        INSERT INTO users (username, password_hash, full_name, email, role, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ('cashier', password_hash, 'Cashier User', 'cashier@store.com', 'cashier', 1))
    
    conn.commit()
    
    print("\n" + "=" * 60)
    print("✅ Cashier account created successfully!")
    print("=" * 60)
    print("  Username: cashier")
    print("  Password: cashier123")
    print("  Role: cashier")
    print("  Active: Yes")
    print("=" * 60)
    
    # Verify account
    cursor.execute("SELECT id, username, role, is_active FROM users WHERE username = 'cashier'")
    user = cursor.fetchone()
    if user:
        print(f"\n✅ Verification:")
        print(f"   ID: {user[0]}")
        print(f"   Username: {user[1]}")
        print(f"   Role: {user[2]}")
        print(f"   Active: {user[3]}")
    
    # Verify password works
    cursor.execute("SELECT password_hash FROM users WHERE username = 'cashier'")
    result = cursor.fetchone()
    if result:
        test_password = 'cashier123'
        if bcrypt.checkpw(test_password.encode('utf-8'), result[0].encode('utf-8')):
            print("   ✅ Password verification: SUCCESS")
        else:
            print("   ❌ Password verification: FAILED - Please recreate the account")
    
    # List all users
    cursor.execute("SELECT id, username, role, is_active FROM users")
    users = cursor.fetchall()
    print("\n📋 All users:")
    for u in users:
        print(f"   ID: {u[0]}, Username: {u[1]}, Role: {u[2]}, Active: {u[3]}")
    
except sqlite3.Error as e:
    print(f"❌ Database error: {e}")
finally:
    conn.close()

print("\n" + "=" * 60)
print("📝 HOW TO LOGIN:")
print("   Go to: http://127.0.0.1:5000/login")
print("")
print("   👑 For Owner:")
print("      Select 'Owner' role")
print("      Username: admin")
print("      Password: admin123")
print("")
print("   🛒 For Cashier:")
print("      Select 'Cashier' role")
print("      Username: cashier")
print("      Password: cashier123")
print("=" * 60)
