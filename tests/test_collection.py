from peruvian_medical_misinformation.collection import (
    canonicalize_url,
    collect_url,
    is_allowed_domain,
)


def test_canonicalize_url_removes_tracking_parameters():
    assert (
        canonicalize_url("https://www.elcomercio.pe/noticia?utm_source=x&id=7#fragment")
        == "https://www.elcomercio.pe/noticia?id=7"
    )


def test_subdomain_is_allowed_but_other_domain_is_not():
    assert is_allowed_domain("https://salud.elcomercio.pe/a", ["elcomercio.pe"])
    assert not is_allowed_domain("https://example.com/a", ["elcomercio.pe"])


class FakeResponse:
    status_code = 200
    url = "https://elcomercio.pe/noticia"
    headers = {"content-type": "text/html; charset=utf-8"}
    text = """
    <html><head><meta property="og:title" content="Noticia médica">
    <meta property="article:published_time" content="2026-09-24"></head>
    <body><p>Una afirmación médica suficientemente larga para probar la extracción del texto de una noticia real.</p>
    <p>La noticia contiene información adicional sobre salud pública y evidencia científica que debe conservarse para la revisión.</p>
    <p>Este tercer párrafo completa el tamaño mínimo del registro y permite comprobar que el extractor conserva el contenido informativo.</p>
    <p>La información se mantiene separada de la etiqueta y de las referencias que serán completadas durante la anotación humana.</p></body></html>
    """

    def raise_for_status(self):
        return None


class FakeClient:
    def get(self, url):
        return FakeResponse()


class ExternalRedirectResponse(FakeResponse):
    url = "https://example.com/noticia"


class ExternalRedirectClient:
    def get(self, url):
        return ExternalRedirectResponse()


def test_collect_url_returns_traceable_record():
    record = collect_url(
        FakeClient(),
        url="https://elcomercio.pe/noticia?utm_campaign=test",
        source_id="el_comercio",
        source_name="El Comercio",
        allowed_domains=["elcomercio.pe"],
    )
    assert record["content_status"] == "ok"
    assert record["source_name"] == "El Comercio"
    assert record["canonical_url"] == "https://elcomercio.pe/noticia"
    assert record["title"] == "Noticia médica"
    assert record["content_hash"]


def test_collect_url_rejects_external_redirect():
    record = collect_url(
        ExternalRedirectClient(),
        url="https://elcomercio.pe/noticia",
        source_id="el_comercio",
        source_name="El Comercio",
        allowed_domains=["elcomercio.pe"],
    )
    assert record["content_status"] == "redirect_not_allowed"
