import bcrypt
import sqlite3
from pathlib import Path
import getpass

def get_db():
    db_path = Path(__file__).parent / "data" / "sari_sari_pos.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")
    return sqlite3.connect(str(db_path))

def create_user(username, password, full_name, email, role='cashier'):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            print(f"❌ User '{username}' already exists")
            return False
        
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute("""
            INSERT INTO users (username, password_hash, full_name, email, role, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, password_hash, full_name, email, role, 1))
        
        conn.commit()
        print(f"✅ User '{username}' created successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        conn.close()

def list_users():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, username, full_name, role, is_active FROM users")
    users = cursor.fetchall()
    
    print("\n📋 Users:")
    print("-" * 60)
    for user in users:
        status = "✅ Active" if user[4] else "❌ Inactive"
        print(f"  {user[0]}. {user[1]} ({user[2]}) - {user[3]} - {status}")
    print("-" * 60)
    conn.close()

def reset_password(username, new_password):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            print(f"❌ User '{username}' not found")
            return False
        
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, username))
        conn.commit()
        
        print(f"✅ Password reset for '{username}'")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        conn.close()

def delete_user(username):
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        print(f"✅ User '{username}' deleted")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("  USER MANAGEMENT")
    print("=" * 60)
    print("1. Create Cashier")
    print("2. List Users")
    print("3. Reset Password")
    print("4. Delete User")
    print("5. Create Admin (Owner)")
    print("=" * 60)
    
    choice = input("Select option (1-5): ").strip()
    
    if choice == '1':
        create_user('cashier', 'cashier123', 'Cashier User', 'cashier@store.com', 'cashier')
    elif choice == '2':
        list_users()
    elif choice == '3':
        username = input("Username: ").strip()
        new_password = getpass.getpass("New password: ").strip()
        reset_password(username, new_password)
    elif choice == '4':
        username = input("Username to delete: ").strip()
        confirm = input(f"Are you sure you want to delete '{username}'? (yes/no): ").strip().lower()
        if confirm == 'yes':
            delete_user(username)
    elif choice == '5':
        create_user('admin2', 'admin123', 'Admin User', 'admin2@store.com', 'owner')
    else:
        print("Invalid option")