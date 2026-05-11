"""Script de utilidad para generar un par de claves RS256 para la firma JWT.

Ejecutar una sola vez durante la configuración inicial:
    uv run python scripts/generate_keys.py
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_key_pair(key_size=2048) -> tuple[str, str]:
    """Genera un par de claves RSA (privada y pública) con el tamaño
    especificado."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )

    # Serializar la clave privada a PEM
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    # Serializar la clave pública a PEM
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    return private_pem, public_pem


# Punto de entrada del script
def main() -> None:
    private_pem, public_pem = generate_rsa_key_pair()

    # Guardar las claves en archivos
    keys_dir = Path("keys")
    keys_dir.mkdir(exist_ok=True)

    with open(keys_dir / "private_key.pem", "w") as private_file:
        private_file.write(private_pem)

    with open(keys_dir / "public_key.pem", "w") as public_file:
        public_file.write(public_pem)

    print("Claves RSA generadas y guardadas en la carpeta 'keys'.")


if __name__ == "__main__":
    main()
