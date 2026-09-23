"""
Testes das funcoes de dados do dashboard.py (carregamento do historico
local e leitura de confirmacao na nuvem). A renderizacao Streamlit em si
(main()) nao e testada aqui pois depende de um script run context real.
"""

import sqlite3

import pandas as pd
import pytest

import dashboard
import gateway


@pytest.fixture
def db_com_leituras(tmp_path, monkeypatch):
    caminho = tmp_path / "test_monitor.db"
    monkeypatch.setattr(gateway, "DB_PATH", caminho)
    monkeypatch.setattr(dashboard, "DB_PATH", caminho)
    gateway.init_db()

    for i, nivel in enumerate(["baixo", "moderado", "alto"]):
        gateway.salvar_local(
            gateway.normalizar_payload(
                {"device_id": "esp01", "valor_sensor": 100 * i, "decibeis": 40.0 + 10 * i, "nivel": nivel}
            )
        )
    return caminho


class TestCarregarHistoricoLocal:
    def test_banco_inexistente_retorna_dataframe_vazio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dashboard, "DB_PATH", tmp_path / "nao_existe.db")
        df = dashboard.carregar_historico_local.__wrapped__()
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_retorna_colunas_esperadas_e_horario_derivado(self, db_com_leituras):
        df = dashboard.carregar_historico_local.__wrapped__()

        assert not df.empty
        assert len(df) == 3
        assert "horario" in df.columns
        assert pd.api.types.is_datetime64_any_dtype(df["horario"])

    def test_ordenacao_e_crescente_por_horario(self, db_com_leituras):
        df = dashboard.carregar_historico_local.__wrapped__()
        assert df["horario"].is_monotonic_increasing

    def test_limite_e_respeitado(self, db_com_leituras):
        df = dashboard.carregar_historico_local.__wrapped__(limite=1)
        assert len(df) == 1


class TestBuscarConfirmacaoCloud:
    def test_sucesso_retorna_ultimo_feed(self, monkeypatch):
        class RespostaFake:
            def raise_for_status(self):
                pass

            def json(self):
                return {"feeds": [{"created_at": "2026-01-01T00:00:00Z"}, {"created_at": "2026-01-02T00:00:00Z"}]}

        monkeypatch.setattr(dashboard.requests, "get", lambda *a, **k: RespostaFake())

        resultado = dashboard.buscar_confirmacao_cloud()
        assert resultado["created_at"] == "2026-01-02T00:00:00Z"

    def test_sem_feeds_retorna_none(self, monkeypatch):
        class RespostaFake:
            def raise_for_status(self):
                pass

            def json(self):
                return {"feeds": []}

        monkeypatch.setattr(dashboard.requests, "get", lambda *a, **k: RespostaFake())
        assert dashboard.buscar_confirmacao_cloud() is None

    def test_falha_de_rede_retorna_none_sem_lancar(self, monkeypatch):
        def fake_get(*args, **kwargs):
            raise dashboard.requests.RequestException("sem conexao")

        monkeypatch.setattr(dashboard.requests, "get", fake_get)
        assert dashboard.buscar_confirmacao_cloud() is None

    def test_resposta_http_com_erro_retorna_none(self, monkeypatch):
        class RespostaFake:
            def raise_for_status(self):
                raise dashboard.requests.HTTPError("404")

        monkeypatch.setattr(dashboard.requests, "get", lambda *a, **k: RespostaFake())
        assert dashboard.buscar_confirmacao_cloud() is None
