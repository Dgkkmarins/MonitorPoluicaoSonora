"""
Teste de integracao ponta a ponta (sem hardware real):

    JSON simulando o ESP8266 --POST--> gateway.py --> SQLite local
                                            |--> ThingSpeak (mockado)
    dashboard.py le o mesmo SQLite e devolve os dados prontos para o grafico.

Isso cobre o fluxo Sensor -> ESP8266 -> Wi-Fi -> Python -> Cloud -> Dashboard
descrito nas Entregas 4 e 5, validando que o dado que "sai do sensor" chega
intacto (mesmo nivel/decibeis) ate a camada que alimenta o dashboard.
"""

import pytest

import dashboard
import gateway


@pytest.fixture
def ambiente_integrado(tmp_path, monkeypatch):
    caminho = tmp_path / "fluxo.db"
    monkeypatch.setattr(gateway, "DB_PATH", caminho)
    monkeypatch.setattr(dashboard, "DB_PATH", caminho)
    gateway.init_db()

    chamadas_thingspeak = []

    def fake_get(url, params, timeout):
        chamadas_thingspeak.append(params)
        return type("R", (), {"status_code": 200, "text": "1"})()

    monkeypatch.setattr(gateway.requests, "get", fake_get)

    gateway.app.config["TESTING"] = True
    client = gateway.app.test_client()
    return client, chamadas_thingspeak


def payload_do_esp(valor_sensor, decibeis, nivel):
    """Mesmo formato de JSON que o firmware .ino monta em enviarDados()."""
    return {
        "device_id": "esp8266_som_01",
        "valor_sensor": valor_sensor,
        "decibeis": decibeis,
        "nivel": nivel,
        "uptime_ms": 123456,
    }


def test_uma_leitura_do_sensor_chega_intacta_ate_o_dashboard(ambiente_integrado):
    client, chamadas_thingspeak = ambiente_integrado

    resposta = client.post("/dados", json=payload_do_esp(700, 82.7, "alto"))
    assert resposta.status_code == 200

    # 1. chegou na "nuvem" (ThingSpeak mockado) com o campo de nivel correto
    assert len(chamadas_thingspeak) == 1
    assert chamadas_thingspeak[0]["field3"] == gateway.NIVEL_PARA_CODIGO["ALTO"]

    # 2. o dashboard consegue ler exatamente essa leitura do banco local
    df = dashboard.carregar_historico_local.__wrapped__()
    assert len(df) == 1
    linha = df.iloc[0]
    assert linha["valor_sensor"] == 700
    assert linha["decibeis"] == 82.7
    assert linha["nivel"] == "ALTO"


def test_varias_leituras_seguidas_mantem_ordem_cronologica_no_dashboard(ambiente_integrado):
    client, _ = ambiente_integrado

    sequencia = [(100, 40.0, "baixo"), (400, 60.0, "moderado"), (800, 90.0, "critico")]
    for valor, db, nivel in sequencia:
        resposta = client.post("/dados", json=payload_do_esp(valor, db, nivel))
        assert resposta.status_code == 200

    df = dashboard.carregar_historico_local.__wrapped__()

    assert list(df["nivel"]) == ["BAIXO", "MODERADO", "CRITICO"]
    assert df["horario"].is_monotonic_increasing


def test_dashboard_nao_trava_quando_thingspeak_esta_fora_do_ar(ambiente_integrado, monkeypatch):
    client, _ = ambiente_integrado

    def fake_get_com_falha(*args, **kwargs):
        raise gateway.requests.RequestException("cloud indisponivel")

    monkeypatch.setattr(gateway.requests, "get", fake_get_com_falha)

    resposta = client.post("/dados", json=payload_do_esp(500, 70.0, "alto"))

    # gravacao local deve funcionar mesmo com a nuvem fora do ar
    assert resposta.status_code == 200
    df = dashboard.carregar_historico_local.__wrapped__()
    assert len(df) == 1


def test_payload_malformado_do_esp_nao_gera_leitura_falsa_no_dashboard(ambiente_integrado):
    client, _ = ambiente_integrado

    resposta = client.post("/dados", json={"decibeis": 50.0})  # falta valor_sensor
    assert resposta.status_code == 400

    df = dashboard.carregar_historico_local.__wrapped__()
    assert df.empty
