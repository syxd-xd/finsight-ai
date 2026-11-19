from database import test_database_connection

if __name__ == "__main__":
    try:
        result = test_database_connection()
        print("MySQL connection successful!")
        print(result)

    except Exception as error:
        print("MySQL connection failed.")
        print(error)
