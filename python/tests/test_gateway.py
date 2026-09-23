"""
Testes do gateway.py: normalizacao do payload do ESP8266, persistencia
local (SQLite), envio para o ThingSpeak (mockado) e os endpoints Flask.
"""

import pytest

import gateway


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    caminho = tmp_path / "test_monitor.db"
    monkeypatch.setattr(gateway, "DB_PATH", caminho)
    gateway.init_db()
    return caminho


@pytest.fixture
def client(db_path):
    gateway.app.config["TESTING"] = True
    return gateway.app.test_client()


class TestNormalizarPayload:
    def test_payload_completo_normaliza_tipos_e_nivel(self):
        bruto = {
            "device_id": "esp8266_som_01",
            "valor_sensor": 512,
            "decibeis": 65.4321,
            "nivel": "moderado",
        }
        resultado = gateway.normalizar_payload(bruto)

        assert resultado["device_id"] == "esp8266_som_01"
        assert resultado["valor_sensor"] == 512
        assert resultado["decibeis"] == 65.43  # arredondado para 2 casas
        assert resultado["nivel"] == "MODERADO"  # normalizado para maiusculo
        assert isinstance(resultado["timestamp"], float)

    def test_campos_opcionais_ausentes_usam_default(self):
        bruto = {"valor_sensor": 300, "decibeis": 40.0}
        resultado = gateway.normalizar_payload(bruto)

        assert resultado["device_id"] == "desconhecido"
        assert resultado["nivel"] == "DESCONHECIDO"

    def test_valor_sensor_ausente_gera_keyerror(self):
        with pytest.raises(KeyError):
            gateway.normalizar_payload({"decibeis": 40.0})

    def test_decibeis_nao_numerico_gera_valueerror(self):
        with pytest.raises(ValueError):
            gateway.normalizar_payload({"valor_sensor": 1, "decibeis": "abc"})

    def test_valor_sensor_string_numerica_e_convertido(self):
        resultado = gateway.normalizar_payload({"valor_sensor": "700", "decibeis": "80.0"})
        assert resultado["valor_sensor"] == 700
        assert resultado["decibeis"] == 80.0


class TestPersistenciaLocal:
    def test_salvar_local_grava_um_registro(self, db_path):
        leitura = gateway.normalizar_payload(
            {"device_id": "d1", "valor_sensor": 100, "decibeis": 55.5, "nivel": "alto"}
        )
        gateway.salvar_local(leitura)

        conn = gateway.get_db()
        linhas = conn.execute("SELECT * FROM leituras").fetchall()
        conn.close()

        assert len(linhas) == 1
        assert linhas[0]["nivel"] == "ALTO"
        assert linhas[0]["valor_sensor"] == 100

    def test_multiplas_leituras_mantem_ordem_de_insercao(self, db_path):
        for i in range(5):
            gateway.salvar_local(
                gateway.normalizar_payload({"valor_sensor": i, "decibeis": float(i)})
            )

        conn = gateway.get_db()
        linhas = conn.execute("SELECT valor_sensor FROM leituras ORDER BY id ASC").fetchall()
        conn.close()

        assert [linha["valor_sensor"] for linha in linhas] == [0, 1, 2, 3, 4]


class TestEnvioThingSpeak:
    def test_envia_parametros_corretos_para_a_api(self, monkeypatch):
        chamadas = {}

        class RespostaFake:
            status_code = 200
            text = "1"

        def fake_get(url, params, timeout):
            chamadas["url"] = url
            chamadas["params"] = params
            return RespostaFake()

        monkeypatch.setattr(gateway.requests, "get", fake_get)

        leitura = {"valor_sensor": 400, "decibeis": 72.5, "nivel": "ALTO"}
        gateway.enviar_para_thingspeak(leitura)

        assert chamadas["url"] == gateway.THINGSPEAK_URL
        assert chamadas["params"]["field1"] == 400
        assert chamadas["params"]["field2"] == 72.5
        assert chamadas["params"]["field3"] == 3  # ALTO -> codigo 3

    def test_nivel_desconhecido_usa_codigo_zero(self, monkeypatch):
        capturado = {}

        def fake_get(url, params, timeout):
            capturado.update(params)
            return type("R", (), {"status_code": 200, "text": "1"})()

        monkeypatch.setattr(gateway.requests, "get", fake_get)
        gateway.enviar_para_thingspeak({"valor_sensor": 1, "decibeis": 1.0, "nivel": "XYZ"})

        assert capturado["field3"] == 0

    def test_falha_de_rede_nao_derruba_o_gateway(self, monkeypatch):
        def fake_get(*args, **kwargs):
            raise gateway.requests.RequestException("timeout")

        monkeypatch.setattr(gateway.requests, "get", fake_get)

        # nao deve lancar excecao para quem chamou
        gateway.enviar_para_thingspeak({"valor_sensor": 1, "decibeis": 1.0, "nivel": "BAIXO"})


class TestEndpointDados:
    def test_post_valido_retorna_200_e_grava_no_banco(self, client, monkeypatch):
        monkeypatch.setattr(gateway, "enviar_para_thingspeak", lambda leitura: None)

        payload = {
            "device_id": "esp8266_som_01",
            "valor_sensor": 620,
            "decibeis": 78.3,
            "nivel": "alto",
        }
        resposta = client.post("/dados", json=payload)

        assert resposta.status_code == 200
        corpo = resposta.get_json()
        assert corpo["status"] == "ok"
        assert corpo["leitura"]["nivel"] == "ALTO"
        assert corpo["leitura"]["valor_sensor"] == 620

    def test_post_forwarding_falho_nao_impede_gravacao_local(self, client, monkeypatch):
        def fake_get(*args, **kwargs):
            raise gateway.requests.RequestException("sem internet")

        monkeypatch.setattr(gateway.requests, "get", fake_get)

        resposta = client.post(
            "/dados", json={"valor_sensor": 1, "decibeis": 1.0, "nivel": "baixo"}
        )

        assert resposta.status_code == 200
        assert len(client.get("/leituras").get_json()) == 1

    def test_post_sem_json_retorna_400(self, client):
        resposta = client.post("/dados", data="isso nao e json", content_type="text/plain")
        assert resposta.status_code == 400

    def test_post_sem_campo_obrigatorio_retorna_400(self, client):
        resposta = client.post("/dados", json={"decibeis": 10.0})
        assert resposta.status_code == 400
        assert "erro" in resposta.get_json()

    def test_post_decibeis_invalido_retorna_400(self, client):
        resposta = client.post(
            "/dados", json={"valor_sensor": 1, "decibeis": "nao-e-numero"}
        )
        assert resposta.status_code == 400


class TestEndpointLeituras:
    def test_get_leituras_retorna_historico_completo(self, client, monkeypatch):
        monkeypatch.setattr(gateway, "enviar_para_thingspeak", lambda leitura: None)
        for i in range(3):
            client.post("/dados", json={"valor_sensor": i, "decibeis": float(i), "nivel": "baixo"})

        resposta = client.get("/leituras")
        assert resposta.status_code == 200
        assert len(resposta.get_json()) == 3

    def test_get_leituras_respeita_limite(self, client, monkeypatch):
        monkeypatch.setattr(gateway, "enviar_para_thingspeak", lambda leitura: None)
        for i in range(5):
            client.post("/dados", json={"valor_sensor": i, "decibeis": float(i), "nivel": "baixo"})

        resposta = client.get("/leituras?limite=2")
        assert len(resposta.get_json()) == 2

    def test_get_leituras_vazio_quando_nao_ha_dados(self, client):
        resposta = client.get("/leituras")
        assert resposta.status_code == 200
        assert resposta.get_json() == []
