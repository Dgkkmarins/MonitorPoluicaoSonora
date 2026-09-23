"""
Gateway local: recebe o JSON do ESP8266 via HTTP,
grava um historico local (SQLite) e repassa a leitura
para a nuvem (ThingSpeak).

Arquitetura: Sensor -> ESP8266 -> Wi-Fi -> Python (este arquivo) -> Cloud
"""

import sqlite3
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, request

# ------------------------------------------
# CONFIGURACAO
# ------------------------------------------
THINGSPEAK_WRITE_API_KEY = "COLOQUE_SUA_WRITE_API_KEY_AQUI"
THINGSPEAK_URL = "https://api.thingspeak.com/update"

# ThingSpeak so aceita numeros nos fields, entao convertemos o nivel
# (texto) num codigo numerico para poder ser plotado no grafico da nuvem.
NIVEL_PARA_CODIGO = {
    "BAIXO": 1,
    "MODERADO": 2,
    "ALTO": 3,
    "CRITICO": 4,
}

DB_PATH = Path(__file__).parent / "monitor.db"

app = Flask(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leituras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            valor_sensor INTEGER,
            decibeis REAL,
            nivel TEXT,
            timestamp REAL
        )
        """
    )
    conn.commit()
    conn.close()


def normalizar_payload(dados: dict) -> dict:
    """Valida e normaliza o JSON recebido do ESP antes de gravar/enviar."""
    return {
        "device_id": str(dados.get("device_id", "desconhecido")),
        "valor_sensor": int(dados["valor_sensor"]),
        "decibeis": round(float(dados["decibeis"]), 2),
        "nivel": str(dados.get("nivel", "DESCONHECIDO")).upper(),
        "timestamp": time.time(),
    }


def salvar_local(leitura: dict):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO leituras (device_id, valor_sensor, decibeis, nivel, timestamp)
        VALUES (:device_id, :valor_sensor, :decibeis, :nivel, :timestamp)
        """,
        leitura,
    )
    conn.commit()
    conn.close()


def enviar_para_thingspeak(leitura: dict):
    codigo_nivel = NIVEL_PARA_CODIGO.get(leitura["nivel"], 0)
    params = {
        "api_key": THINGSPEAK_WRITE_API_KEY,
        "field1": leitura["valor_sensor"],
        "field2": leitura["decibeis"],
        "field3": codigo_nivel,
    }
    try:
        resposta = requests.get(THINGSPEAK_URL, params=params, timeout=5)
        print(f"[ThingSpeak] status={resposta.status_code} entry_id={resposta.text}")
    except requests.RequestException as erro:
        print(f"[ThingSpeak] falha ao enviar: {erro}")


@app.route("/dados", methods=["POST"])
def receber_dados():
    bruto = request.get_json(force=True, silent=True)
    if not bruto:
        return jsonify({"erro": "JSON invalido ou ausente"}), 400

    try:
        leitura = normalizar_payload(bruto)
    except (KeyError, ValueError, TypeError) as erro:
        return jsonify({"erro": f"payload invalido: {erro}"}), 400

    salvar_local(leitura)
    enviar_para_thingspeak(leitura)

    print(f"[Gateway] {leitura}")
    return jsonify({"status": "ok", "leitura": leitura}), 200


@app.route("/leituras", methods=["GET"])
def listar_leituras():
    """Usado pelo dashboard para ler o historico local."""
    limite = int(request.args.get("limite", 100))
    conn = get_db()
    linhas = conn.execute(
        "SELECT * FROM leituras ORDER BY id DESC LIMIT ?", (limite,)
    ).fetchall()
    conn.close()
    return jsonify([dict(linha) for linha in linhas])


if __name__ == "__main__":
    init_db()
    print("Gateway rodando em http://0.0.0.0:5000")
    print("Endpoint que o ESP8266 deve chamar: POST /dados")
    app.run(host="0.0.0.0", port=5000)
