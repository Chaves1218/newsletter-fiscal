import requests
import resend
import os
import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta

# ── Configurações ──────────────────────────────────────────────
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
FROM_EMAIL     = "newsletter@resend.dev"
TO_EMAILS      = ["guilherme.chaves@cooperflora.com.br"]

HEADERS = {"User-Agent": "Mozilla/5.0 (newsletter-fiscal-cooperflora)"}

# ── Período: semana anterior (seg a sex) ───────────────────────
hoje        = date.today()
data_inicio = hoje - timedelta(days=7)
data_fim    = hoje - timedelta(days=1)

# ── Termos de busca ────────────────────────────────────────────
TERMOS = [
    "ICMS", "PIS", "COFINS", "IPI", "CSLL", "IRPJ",
    "reforma tributaria", "nota fiscal", "CT-e",
    "cooperativa", "floricultura", "DIFAL",
    "substituicao tributaria", "Simples Nacional",
    "instrucao normativa", "portaria", "convenio ICMS",
]

# ── API LexML (Senado Federal) — SRU ──────────────────────────
def buscar_lexml() -> list[dict]:
    """
    API pública do LexML — mantida pelo Senado Federal.
    Sem cadastro, sem autenticação. Padrão SRU internacional.
    Cobre: leis, decretos, portarias, instruções normativas,
    convênios ICMS, ajustes SINIEF, protocolos — tudo publicado no DOU.
    """
    NS = {
        "srw":    "http://www.loc.gov/zing/srw/",
        "dc":     "http://purl.org/dc/elements/1.1/",
        "srw_dc": "info:srw/schema/1/dc-schema",
    }

    resultados = {}
    ini = data_inicio.strftime("%Y-%m-%d")
    fim = data_fim.strftime("%Y-%m-%d")

    for termo in TERMOS:
        try:
            # Busca por termo + filtro de data de publicação
            query = f'dc.description any "{termo}" and dc.date >= "{ini}" and dc.date <= "{fim}"'
            params = {
                "operation":      "searchRetrieve",
                "version":        "1.1",
                "query":          query,
                "maximumRecords": "10",
                "recordSchema":   "dc",
            }
            r = requests.get(
                "https://www.lexml.gov.br/busca/SRU",
                params=params,
                headers=HEADERS,
                timeout=20,
            )
            if r.status_code != 200:
                continue

            root = ET.fromstring(r.content)
            records = root.findall(".//srw:record", NS)

            for rec in records:
                data_el   = rec.find(".//dc:date",  NS)
                titulo_el = rec.find(".//dc:title", NS)
                urn_el    = rec.find(".//urn",       {})

                # Fallback sem namespace para urn
                if urn_el is None:
                    for el in rec.iter():
                        if el.tag.endswith("urn") or el.tag == "urn":
                            urn_el = el
                            break

                titulo = titulo_el.text.strip() if titulo_el is not None and titulo_el.text else ""
                data_pub = data_el.text.strip() if data_el is not None and data_el.text else ""
                urn    = urn_el.text.strip() if urn_el is not None and urn_el.text else ""
                link   = f"https://www.lexml.gov.br/urn/{urn}" if urn else "https://www.lexml.gov.br"

                # Formata data
                try:
                    data_fmt = datetime.strptime(data_pub, "%Y-%m-%d").strftime("%d/%m/%Y")
                except Exception:
                    data_fmt = data_pub

                if titulo and titulo not in resultados:
                    resultados[titulo] = {
                        "titulo": titulo,
                        "resumo": f"Publicado em {data_fmt} — clique para acessar o texto completo no portal LexML do Senado Federal.",
                        "url":    link,
                        "orgao":  "LexML / Senado Federal",
                        "data":   data_fmt,
                    }

        except Exception as e:
            print(f"[ERRO LexML] {termo}: {e}")

    items = list(resultados.values())
    items.sort(key=lambda x: x.get("data",""), reverse=True)
    print(f"     {len(items)} itens encontrados no LexML")
    return items[:15]

# ── Receita Federal — RSS ──────────────────────────────────────
def buscar_receita() -> list[dict]:
    kws = ["icms","pis","cofins","ipi","csll","irpj","tributar",
           "cooperativ","reforma","nota fiscal","sped","difal",
           "instrucao normativa","portaria","obrigacao acessoria"]
    urls = [
        "https://www.gov.br/receitafederal/pt-br/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true",
        "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true",
    ]
    items  = []
    vistos = set()
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:40]:
                pub = e.get("published_parsed") or e.get("updated_parsed")
                if pub:
                    pub_date = date(*pub[:3])
                    if not (data_inicio <= pub_date <= data_fim):
                        continue
                txt = (e.get("title","") + e.get("summary","")).lower()
                if any(k in txt for k in kws):
                    titulo = e.get("title","")
                    if titulo not in vistos:
                        vistos.add(titulo)
                        pub_fmt = date(*pub[:3]).strftime("%d/%m/%Y") if pub else "—"
                        items.append({
                            "titulo": titulo,
                            "resumo": e.get("summary","")[:300],
                            "url":    e.get("link",""),
                            "orgao":  "Receita Federal",
                            "data":   pub_fmt,
                        })
        except Exception as ex:
            print(f"[ERRO Receita] {ex}")

    items.sort(key=lambda x: x.get("data",""), reverse=True)
    print(f"     {len(items[:8])} itens encontrados na Receita Federal")
    return items[:8]

# ── Montar HTML ────────────────────────────────────────────────
def build_html(lexml_items, receita_items) -> str:
    hoje_fmt   = datetime.now().strftime("%d/%m/%Y")
    inicio_fmt = data_inicio.strftime("%d/%m/%Y")
    fim_fmt    = data_fim.strftime("%d/%m/%Y")
    total      = len(lexml_items) + len(receita_items)

    def render_items(items):
        if not items:
            return '<p style="color:#999;font-style:italic;">Nenhuma publicação relevante encontrada nesta semana.</p>'
        por_data = {}
        for it in items:
            d = it.get("data","—")
            por_data.setdefault(d, []).append(it)
        html = ""
        for d in sorted(por_data.keys(), reverse=True):
            html += f'<p style="font-size:12px;font-weight:bold;color:#4a7c3f;margin:12px 0 6px;">📅 {d}</p>'
            for it in por_data[d]:
                orgao = f'<span style="font-size:11px;color:#888;">{it.get("orgao","")}</span><br>' if it.get("orgao") else ""
                html += f"""
                <div style="margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid #eee;">
                  {orgao}
                  <a href="{it['url']}" style="color:#1a5276;font-weight:bold;font-size:14px;text-decoration:none;">{it['titulo']}</a>
                  <p style="color:#555;font-size:13px;margin:4px 0 0;">{it['resumo']}...</p>
                </div>"""
        return html

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px;">
<div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;">

  <div style="background:#4a7c3f;padding:24px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:20px;">Newsletter Fiscal Semanal — Cooperflora</h1>
    <p style="color:#d4edda;margin:6px 0 0;font-size:13px;">
      Semana de {inicio_fmt} a {fim_fmt} · Enviado em {hoje_fmt}
    </p>
  </div>

  <!-- Estatísticas -->
  <div style="background:#e8f5e9;padding:12px 28px;font-size:13px;color:#2e7d32;border-bottom:1px solid #c8e6c9;">
    ✅ <strong>{total} publicações relevantes</strong> encontradas nesta semana
    · LexML/Legislação: {len(lexml_items)} · Receita Federal: {len(receita_items)}<br>
    <a href="https://www.lexml.gov.br" style="color:#1a5276;">🔗 Portal LexML — Senado Federal</a>
    &nbsp;|&nbsp;
    <a href="https://www.gov.br/receitafederal/pt-br/assuntos/noticias" style="color:#1a5276;">🔗 Notícias Receita Federal</a>
  </div>

  <!-- LexML -->
  <div style="padding:20px 28px;border-bottom:2px solid #4a7c3f;">
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">
      📋 Legislação Federal — LexML / Senado Federal
    </h2>
    <p style="font-size:12px;color:#888;margin:0 0 12px;">
      Inclui: Leis · Decretos · Portarias · Instruções Normativas · Convênios ICMS · Protocolos CONFAZ
    </p>
    {render_items(lexml_items)}
  </div>

  <!-- Receita Federal -->
  <div style="padding:20px 28px;">
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">
      🏛️ Receita Federal — Notícias e Atos
    </h2>
    {render_items(receita_items)}
  </div>

  <div style="background:#f0f0f0;padding:16px 28px;font-size:11px;color:#999;text-align:center;">
    Newsletter gerada automaticamente toda segunda-feira às 10h00 | Cooperflora<br>
    Fontes: LexML (Senado Federal) · Receita Federal
  </div>

</div>
</body></html>"""

# ── Enviar ─────────────────────────────────────────────────────
def send_newsletter(html: str):
    resend.api_key = RESEND_API_KEY
    resp = resend.Emails.send({
        "from":    FROM_EMAIL,
        "to":      TO_EMAILS,
        "subject": f"📋 Newsletter Fiscal Cooperflora — Semana {data_inicio.strftime('%d/%m')} a {data_fim.strftime('%d/%m/%Y')}",
        "html":    html,
    })
    print(f"[OK] E-mail enviado! ID: {resp['id']}")

# ── Main ───────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now():%H:%M:%S}] Iniciando coleta semanal ({data_inicio} a {data_fim})...")
    print("  → Consultando LexML (Senado Federal)...")
    lexml_items   = buscar_lexml()
    print("  → Consultando Receita Federal...")
    receita_items = buscar_receita()
    html = build_html(lexml_items, receita_items)
    send_newsletter(html)

if __name__ == "__main__":
    main()
