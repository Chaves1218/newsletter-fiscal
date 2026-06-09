import requests
import resend
import os
from datetime import datetime, date

# ── Configurações ──────────────────────────────────────────────
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
FROM_EMAIL     = "newsletter@resend.dev"
TO_EMAILS      = ["guilherme.chaves@cooperflora.com.br"]

# ── Termos de busca no DOU ─────────────────────────────────────
TERMOS_DOU = [
    "ICMS", "PIS", "COFINS", "IPI", "CSLL", "IRPJ",
    "reforma tributária", "nota fiscal", "CT-e", "DANFE",
    "cooperativa", "floricultura", "folhagem", "horticultura",
    "DIFAL", "SPED", "substituição tributária", "obrigação acessória",
    "Simples Nacional", "contribuição social",
]

# ── API pública do DOU ─────────────────────────────────────────
DOU_API = "https://www.in.gov.br/consulta/-/buscar/dou"

def buscar_dou(termo: str, secao: str = "todos") -> list[dict]:
    """Consulta a API pública do DOU por termo e retorna lista de resultados."""
    hoje = date.today().strftime("%d-%m-%Y")
    params = {
        "q":          termo,
        "s":          secao,        # do1, do2, do3 ou todos
        "exactDate":  hoje,
        "sortType":   0,
    }
    headers = {"User-Agent": "Mozilla/5.0 (newsletter-fiscal-cooperflora)"}
    try:
        r = requests.get(DOU_API, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        items = []
        for hit in data.get("hits", {}).get("hits", [])[:5]:
            src = hit.get("_source", {})
            items.append({
                "titulo":   src.get("titulo", "Sem título"),
                "resumo":   src.get("resumo", src.get("conteudo", ""))[:300],
                "url":      f"https://www.in.gov.br/web/dou/-/ato-{src.get('idOficio', '')}",
                "secao":    src.get("secaoFormatado", ""),
                "orgao":    src.get("orgaoFormatado", ""),
            })
        return items
    except Exception as e:
        print(f"[ERRO DOU] {termo}: {e}")
        return []

# ── Receita Federal — RSS ──────────────────────────────────────
def buscar_receita() -> list[dict]:
    import feedparser
    url = "https://www.gov.br/receitafederal/pt-br/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true"
    kws = ["icms","pis","cofins","ipi","csll","irpj","tributar","cooperativ","reforma","nota fiscal","sped","ecf","efd"]
    try:
        feed = feedparser.parse(url)
        items = []
        for e in feed.entries[:20]:
            txt = (e.get("title","") + e.get("summary","")).lower()
            if any(k in txt for k in kws):
                items.append({
                    "titulo": e.get("title",""),
                    "resumo": e.get("summary","")[:300],
                    "url":    e.get("link",""),
                    "orgao":  "Receita Federal",
                })
        return items[:5]
    except Exception as ex:
        print(f"[ERRO Receita] {ex}")
        return []

# ── CONFAZ — RSS ───────────────────────────────────────────────
def buscar_confaz() -> list[dict]:
    import feedparser
    url = "https://www.confaz.fazenda.gov.br/legislacao/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true"
    try:
        feed = feedparser.parse(url)
        items = []
        for e in feed.entries[:10]:
            items.append({
                "titulo": e.get("title",""),
                "resumo": e.get("summary","")[:300],
                "url":    e.get("link",""),
                "orgao":  "CONFAZ",
            })
        return items[:5]
    except Exception as ex:
        print(f"[ERRO CONFAZ] {ex}")
        return []

# ── Montar HTML ────────────────────────────────────────────────
def build_html(dou_items: list, receita_items: list, confaz_items: list) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")

    def render_items(items):
        if not items:
            return '<p style="color:#999;font-style:italic;">Nenhuma publicação relevante encontrada hoje.</p>'
        html = ""
        for it in items:
            orgao = f'<span style="font-size:11px;color:#888;">{it.get("orgao","")}{" · " + it.get("secao","") if it.get("secao") else ""}</span><br>' if it.get("orgao") else ""
            html += f"""
            <div style="margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #eee;">
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

  <!-- Cabeçalho -->
  <div style="background:#4a7c3f;padding:24px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:20px;">Newsletter Fiscal — Cooperflora</h1>
    <p style="color:#d4edda;margin:6px 0 0;font-size:13px;">Edição de {hoje} · Atualização automática diária</p>
  </div>

  <!-- DOU -->
  <div style="padding:20px 28px;border-bottom:2px solid #4a7c3f;">
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">
      📋 Diário Oficial da União — Publicações Fiscais
    </h2>
    {render_items(dou_items)}
  </div>

  <!-- Receita Federal -->
  <div style="padding:20px 28px;border-bottom:2px solid #4a7c3f;">
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">
      🏛️ Receita Federal — Notícias
    </h2>
    {render_items(receita_items)}
  </div>

  <!-- CONFAZ -->
  <div style="padding:20px 28px;">
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">
      📜 CONFAZ — Atos e Convênios
    </h2>
    {render_items(confaz_items)}
  </div>

  <!-- Rodapé -->
  <div style="background:#f0f0f0;padding:16px 28px;font-size:11px;color:#999;text-align:center;">
    Newsletter gerada automaticamente em {hoje} às 10h00 | Cooperflora<br>
    Fontes: Diário Oficial da União · Receita Federal · CONFAZ
  </div>

</div>
</body></html>"""

# ── Enviar e-mail ──────────────────────────────────────────────
def send_newsletter(html: str):
    resend.api_key = RESEND_API_KEY
    hoje = datetime.now().strftime("%d/%m/%Y")
    resp = resend.Emails.send({
        "from":    FROM_EMAIL,
        "to":      TO_EMAILS,
        "subject": f"📋 Newsletter Fiscal Cooperflora — {hoje}",
        "html":    html,
    })
    print(f"[OK] E-mail enviado! ID: {resp['id']}")

# ── Main ───────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now():%H:%M:%S}] Iniciando coleta...")

    # Busca no DOU — consolida todos os termos, remove duplicatas por título
    print("  → Consultando DOU...")
    dou_dict = {}
    for termo in TERMOS_DOU:
        for item in buscar_dou(termo):
            dou_dict[item["titulo"]] = item
    dou_items = list(dou_dict.values())[:10]
    print(f"     {len(dou_items)} itens encontrados no DOU")

    print("  → Consultando Receita Federal...")
    receita_items = buscar_receita()
    print(f"     {len(receita_items)} itens encontrados")

    print("  → Consultando CONFAZ...")
    confaz_items = buscar_confaz()
    print(f"     {len(confaz_items)} itens encontrados")

    html = build_html(dou_items, receita_items, confaz_items)
    send_newsletter(html)

if __name__ == "__main__":
    main()
