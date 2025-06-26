from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_context.hash("hashed_dummy_password")
print("Hash generado:\n", hashed)
