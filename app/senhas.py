"""Hash de senha com scrypt (biblioteca padrão). Formato autodescritivo:

    scrypt$<n>$<r>$<p>$<sal_base64>$<hash_base64>

Os parâmetros de custo vão dentro do próprio hash: dá para aumentar as constantes abaixo sem invalidar os
hashes antigos (`precisa_rehash` avisa quais ficaram abaixo do custo atual; o login os regrava)."""
import base64
import binascii
import hashlib
import hmac
import secrets

ALGORITMO = "scrypt"
# Custo atual: N=2^15, r=8, p=3 (equivalente mínimo recomendado pela OWASP para scrypt; ~32 MiB de memória).
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 3
SAL_BYTES = 16
HASH_BYTES = 32
# Margem acima de 128*N*r (que é o uso real): o limite padrão do OpenSSL (32 MiB) recusaria N=2^15, r=8.
SCRYPT_MAXMEM = 128 * 1024 * 1024
# Teto aceito ao LER um hash (defesa: um registro adulterado não pode pedir custo absurdo de CPU/memória).
N_MAX, R_MAX, P_MAX = 2 ** 20, 32, 16
# Senha acima disto (em bytes UTF-8) é recusada: evita usar o scrypt como vetor de negação de serviço.
SENHA_MAX_BYTES = 1024


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


def _derivar(senha: bytes, sal: bytes, n: int, r: int, p: int, tamanho: int) -> bytes:
    return hashlib.scrypt(senha, salt=sal, n=n, r=r, p=p, dklen=tamanho, maxmem=SCRYPT_MAXMEM)


def senha_valida_tamanho(senha: str) -> bool:
    return len(senha.encode("utf-8")) <= SENHA_MAX_BYTES


def gerar_hash(senha: str, *, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> str:
    """Hash com sal aleatório novo. Levanta ValueError se a senha passar do limite de tamanho."""
    if not senha_valida_tamanho(senha):
        raise ValueError(f"senha acima do limite de {SENHA_MAX_BYTES} bytes")
    sal = secrets.token_bytes(SAL_BYTES)
    derivado = _derivar(senha.encode("utf-8"), sal, n, r, p, HASH_BYTES)
    return f"{ALGORITMO}${n}${r}${p}${_b64(sal)}${_b64(derivado)}"


def _ler(hash_texto: str | None):
    """(n, r, p, sal, derivado) ou None se o hash for malformado, de outro algoritmo ou de custo fora do teto."""
    try:
        algoritmo, n, r, p, sal, derivado = hash_texto.split("$")
        if algoritmo != ALGORITMO:
            return None
        n, r, p = int(n), int(r), int(p)
        if not (2 <= n <= N_MAX and n & (n - 1) == 0 and 1 <= r <= R_MAX and 1 <= p <= P_MAX):
            return None
        sal, derivado = base64.b64decode(sal, validate=True), base64.b64decode(derivado, validate=True)
        if not sal or not derivado:
            return None
        return n, r, p, sal, derivado
    except (AttributeError, ValueError, binascii.Error):
        return None


def verificar(senha: str, hash_texto: str | None) -> bool:
    """Confere a senha em tempo constante. Hash malformado, algoritmo desconhecido ou senha grande demais
    devolvem False; nunca levanta."""
    try:
        if not isinstance(senha, str) or not senha_valida_tamanho(senha):
            return False
        lido = _ler(hash_texto)
        if lido is None:
            return False
        n, r, p, sal, esperado = lido
        obtido = _derivar(senha.encode("utf-8"), sal, n, r, p, len(esperado))
        return hmac.compare_digest(obtido, esperado)
    except (ValueError, MemoryError, OverflowError):
        return False


def precisa_rehash(hash_texto: str | None) -> bool:
    """True se o hash é válido mas tem custo (ou tamanho de sal/hash) abaixo do atual."""
    lido = _ler(hash_texto)
    if lido is None:
        return False
    n, r, p, sal, derivado = lido
    return n < SCRYPT_N or r < SCRYPT_R or p < SCRYPT_P or len(sal) < SAL_BYTES or len(derivado) < HASH_BYTES
