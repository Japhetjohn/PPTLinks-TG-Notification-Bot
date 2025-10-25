import sqlite3
import json
from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)

class Database:
    """SQLite database handler for bot data"""
    
    def __init__(self, db_path: str = "pptlinks_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Courses table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS courses (
                        course_id TEXT PRIMARY KEY,
                        course_name TEXT,
                        course_data TEXT,
                        data_hash TEXT,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # User-Course subscriptions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_courses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER,
                        course_id TEXT,
                        subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        active BOOLEAN DEFAULT 1,
                        FOREIGN KEY (chat_id) REFERENCES users(chat_id),
                        FOREIGN KEY (course_id) REFERENCES courses(course_id),
                        UNIQUE(chat_id, course_id)
                    )
                """)
                
                # Notifications log table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER,
                        course_id TEXT,
                        notification_type TEXT,
                        content TEXT,
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    def add_user(self, chat_id: int, username: str = None, 
                 first_name: str = None, last_name: str = None):
        """Add or update user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO users 
                    (chat_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                """, (chat_id, username, first_name, last_name))
                conn.commit()
        except Exception as e:
            logger.error(f"Error adding user: {e}")
    
    def subscribe_user_to_course(self, chat_id: int, course_id: str) -> bool:
        """Subscribe a user to a course

        Returns:
            True if this is a new subscription
            False if user was already subscribed (active=1)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check if subscription exists
                cursor.execute("""
                    SELECT active FROM user_courses
                    WHERE chat_id = ? AND course_id = ?
                """, (chat_id, course_id))

                row = cursor.fetchone()

                if row is None:
                    # New subscription - insert
                    cursor.execute("""
                        INSERT INTO user_courses (chat_id, course_id, active)
                        VALUES (?, ?, 1)
                    """, (chat_id, course_id))
                    conn.commit()
                    logger.info(f"New subscription created: user {chat_id}, course {course_id}")
                    return True
                elif row[0] == 0:
                    # Reactivate inactive subscription
                    cursor.execute("""
                        UPDATE user_courses
                        SET active = 1, subscribed_at = CURRENT_TIMESTAMP
                        WHERE chat_id = ? AND course_id = ?
                    """, (chat_id, course_id))
                    conn.commit()
                    logger.info(f"Reactivated subscription: user {chat_id}, course {course_id}")
                    return True
                else:
                    # Already active
                    logger.info(f"Already subscribed: user {chat_id}, course {course_id}")
                    return False

        except Exception as e:
            logger.error(f"Error subscribing user to course: {e}")
            return False
    
    def unsubscribe_user_from_course(self, chat_id: int, course_id: str = None):
        """Unsubscribe user from a course or all courses"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if course_id:
                    cursor.execute("""
                        UPDATE user_courses 
                        SET active = 0 
                        WHERE chat_id = ? AND course_id = ?
                    """, (chat_id, course_id))
                else:
                    # Unsubscribe from all
                    cursor.execute("""
                        UPDATE user_courses 
                        SET active = 0 
                        WHERE chat_id = ?
                    """, (chat_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Error unsubscribing user: {e}")
    
    def get_user_courses(self, chat_id: int) -> List[str]:
        """Get all courses a user is subscribed to"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT course_id FROM user_courses
                    WHERE chat_id = ? AND active = 1
                """, (chat_id,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting user courses: {e}")
            return []
    
    def get_course_subscribers(self, course_id: str) -> List[int]:
        """Get all users subscribed to a course"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT chat_id FROM user_courses
                    WHERE course_id = ? AND active = 1
                """, (course_id,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting course subscribers: {e}")
            return []
    
    def save_course_data(self, course_id: str, course_name: str, 
                         course_data: dict, data_hash: str):
        """Save or update course data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO courses 
                    (course_id, course_name, course_data, data_hash, last_updated)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (course_id, course_name, json.dumps(course_data), data_hash))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving course data: {e}")
    
    def get_course_data(self, course_id: str) -> Optional[Dict]:
        """Get cached course data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT course_data, data_hash FROM courses
                    WHERE course_id = ?
                """, (course_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'data': json.loads(row[0]),
                        'hash': row[1]
                    }
        except Exception as e:
            logger.error(f"Error getting course data: {e}")
        return None
    
    def log_notification(self, chat_id: int, course_id: str, 
                        notification_type: str, content: str):
        """Log sent notification"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO notifications 
                    (chat_id, course_id, notification_type, content)
                    VALUES (?, ?, ?, ?)
                """, (chat_id, course_id, notification_type, content))
                conn.commit()
        except Exception as e:
            logger.error(f"Error logging notification: {e}")
    
    def get_user_stats(self, chat_id: int) -> Dict:
        """Get user statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total courses
                cursor.execute("""
                    SELECT COUNT(*) FROM user_courses
                    WHERE chat_id = ? AND active = 1
                """, (chat_id,))
                total_courses = cursor.fetchone()[0]
                
                # Total notifications received
                cursor.execute("""
                    SELECT COUNT(*) FROM notifications
                    WHERE chat_id = ?
                """, (chat_id,))
                total_notifications = cursor.fetchone()[0]
                
                return {
                    'total_courses': total_courses,
                    'total_notifications': total_notifications
                }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {'total_courses': 0, 'total_notifications': 0}
    
    def cleanup_old_notifications(self, days: int = 30):
        """Delete old notification logs"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM notifications
                    WHERE sent_at < datetime('now', '-' || ? || ' days')
                """, (days,))
                deleted = cursor.rowcount
                conn.commit()
                logger.info(f"Cleaned up {deleted} old notifications")
        except Exception as e:
            logger.error(f"Error cleaning up notifications: {e}")
    
    def get_all_active_subscriptions(self) -> List[tuple]:
        """Get all active user-course pairs for monitoring"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT chat_id, course_id FROM user_courses
                    WHERE active = 1
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting active subscriptions: {e}")
            return []

    def get_subscription_date(self, chat_id: int, course_id: str) -> Optional[str]:
        """Get subscription date for a user-course pair"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT subscribed_at FROM user_courses
                    WHERE chat_id = ? AND course_id = ? AND active = 1
                """, (chat_id, course_id))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting subscription date: {e}")
            return None