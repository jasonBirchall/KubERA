#!/usr/bin/env python3
"""
Reset the Kubera database to start fresh.
Use this script when you want to completely reset the database,
especially after schema changes.
"""

from db import reset_db

if __name__ == "__main__":
    print("Resetting Kubera database...")
    reset_db()
    print("Database reset completed. You can now start the application with a fresh database.")
