from passlib.context import CryptContext
import argparse
import getpass
import sys

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def main():
    parser = argparse.ArgumentParser(
        description="Genera un hash bcrypt compatible para guardar en users.password_hash"
    )
    parser.add_argument(
        "--password",
        "-p",
        help="Contraseña en texto plano (si no se pasa, se pedirá por prompt)",
    )
    args = parser.parse_args()

    if args.password:
        plain = args.password
    else:
        # prompt seguro (no se muestra lo que escribes)
        p1 = getpass.getpass("Nueva contraseña: ")
        p2 = getpass.getpass("Repite la contraseña: ")
        if p1 != p2:
            print("Error: las contraseñas no coinciden.", file=sys.stderr)
            sys.exit(1)
        plain = p1

    hashed = pwd_context.hash(plain)
    # Imprime solo el hash, sin texto adicional, para copiar/pegar fácil
    print(hashed)

if __name__ == "__main__":
    main()
