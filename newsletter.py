import feedparser
import requests
import base64
import os
from datetime import datetime
from resend import Resend

# ── Configurações ──────────────────────────────────────────────
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
FROM_EMAIL     = "newsletter@resend.dev"            # domínio gratuito do Resend, sem DNS próprio
TO_EMAILS      = ["guilherme.chaves@cooperflora.com.br"]
LOGO_PATH      = None                               # logo desativada

# ── Fontes RSS ─────────────────────────────────────────────────
FEEDS = [
    {
        "name": "Diário Oficial da União (DOU) — Seção 1",
        "url": "https://www.in.gov.br/leiturajornal?data=hoje&secao=do1",
        "rss": "https://www.in.gov.br/leiturajornal?data=hoje&secao=do1&tipoPesquisa=0&termoPesquisa=cooperativa+flor+folhagem+ICMS+PIS+COFINS+IPI+CSLL+IRPJ&formato=rss",
    },
    {
        "name": "Receita Federal — Notícias",
        "rss": "https://www.gov.br/receitafederal/pt-br/@@search?portal_type=News+Item&review_state=published&sort_on=effective&sort_order=descending&RSS=true",
    },
    {
        "name": "CONFAZ — Atos",
        "rss": "https://www.confaz.fazenda.gov.br/legislacao/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true",
    },
    {
        "name": "Portal da Fazenda — Legislação Tributária",
        "rss": "https://www.gov.br/fazenda/pt-br/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true",
    },
    {
        "name": "Senado Federal — Legislação",
        "rss": "https://legis.senado.leg.br/rss/legislacao.xml",
    },
    {
        "name": "Câmara dos Deputados — Legislação Tributária",
        "rss": "https://www.camara.leg.br/noticias/rss/keyword/tributario",
    },
]

# ── Palavras-chave filtro ──────────────────────────────────────
KEYWORDS = [
    "icms", "pis", "cofins", "ipi", "csll", "irpj",
    "reforma tributária", "nota fiscal", "danfe", "ct-e", "cte",
    "cooperativa", "flor", "folhagem", "horticultura",
    "difal", "sped", "ecf", "efd", "nfe", "nf-e",
    "simples nacional", "lucro presumido", "obrigação acessória",
    "contribuição social", "imposto de renda", "receita federal",
    "confaz", "convênio icms", "protocolo icms",
]

# ── Funções ────────────────────────────────────────────────────
def logo_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def fetch_feed(feed: dict) -> list[dict]:
    try:
        parsed = feedparser.parse(feed["rss"])
        items = []
        for entry in parsed.entries[:10]:  # máx 10 por fonte
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")
            text = (title + " " + summary).lower()
            if any(kw in text for kw in KEYWORDS):
                items.append({"title": title, "summary": summary[:300], "link": link})
        return items
    except Exception as e:
        print(f"[ERRO] {feed['name']}: {e}")
        return []

def build_html(sections: dict) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")
    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:0; }}
    .container {{ max-width:680px; margin:0 auto; background:#fff; border-radius:8px; overflow:hidden; }}
    .header {{ background:#4a7c3f; padding:24px; text-align:center; }}
    .header img {{ max-height:80px; }}
    .header h1 {{ color:#fff; font-size:18px; margin:12px 0 4px; }}
    .header p {{ color:#d4edda; font-size:13px; margin:0; }}
    .section {{ padding:20px 28px; border-bottom:1px solid #eee; }}
    .section h2 {{ color:#4a7c3f; font-size:15px; border-left:4px solid #4a7c3f; padding-left:10px; }}
    .item {{ margin-bottom:14px; }}
    .item a {{ color:#1a5276; font-weight:bold; text-decoration:none; font-size:14px; }}
    .item p {{ color:#555; font-size:13px; margin:4px 0 0; }}
    .footer {{ background:#f0f0f0; padding:16px 28px; font-size:11px; color:#999; text-align:center; }}
    .badge {{ display:inline-block; background:#4a7c3f; color:#fff; border-radius:4px;
              font-size:11px; padding:2px 8px; margin-bottom:6px; }}
    .empty {{ color:#999; font-size:13px; font-style:italic; }}
  </style>
</head>
<body>
<div class="container">
      <div class="header">
    <h1>Newsletter Fiscal — Cooperflora</h1>
    <p>Edição de {hoje} | Atualização automática diária</p>
  </div>
"""
    for source_name, items in sections.items():
        html += f'<div class="section"><h2>{source_name}</h2>'
        if items:
            for it in items:
                html += f"""
        <div class="item">
          <a href="{it['link']}" target="_blank">{it['title']}</a>
          <p>{it['summary']}...</p>
        </div>"""
        else:
            html += '<p class="empty">Nenhuma publicação relevante encontrada hoje.</p>'
        html += "</div>"

    html += f"""
  <div class="footer">
    Newsletter gerada automaticamente em {hoje} às 10h00 | Cooperflora<br>
    Fontes: DOU · Receita Federal · CONFAZ · Fazenda · Senado · Câmara
  </div>
</div>
</body></html>"""
    return html

def send_newsletter(html: str):
    client = Resend(api_key=RESEND_API_KEY)
    hoje = datetime.now().strftime("%d/%m/%Y")
    params = {
        "from": FROM_EMAIL,
        "to": TO_EMAILS,
        "subject": f"📋 Newsletter Fiscal Cooperflora — {hoje}",
        "html": html,
    }
    resp = client.emails.send(params)
    print(f"[OK] E-mail enviado! ID: {resp.id}")

# ── Main ───────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now():%H:%M:%S}] Iniciando coleta de feeds...")
    logo_b64 = None
    sections = {}
    for feed in FEEDS:
        print(f"  → Coletando: {feed['name']}")
        sections[feed["name"]] = fetch_feed(feed)

    total = sum(len(v) for v in sections.values())
    print(f"[INFO] {total} itens relevantes encontrados.")

    html = build_html(sections)
    send_newsletter(html)

if __name__ == "__main__":
    main()
