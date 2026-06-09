import requests
import resend
import os
import feedparser
from datetime import datetime, date, timedelta
from bs4 import BeautifulSoup

# ── Configurações ──────────────────────────────────────────────
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
FROM_EMAIL     = "newsletter@resend.dev"
TO_EMAILS      = ["guilherme.chaves@cooperflora.com.br"]

HEADERS = {"User-Agent": "Mozilla/5.0 (newsletter-fiscal-cooperflora)"}

# ── Período: semana anterior (seg a sex) ───────────────────────
hoje        = date.today()
data_inicio = hoje - timedelta(days=7)  # última segunda
data_fim    = hoje - timedelta(days=1)  # última sexta

TERMOS_DOU = [
    "ICMS", "PIS COFINS", "IPI", "CSLL IRPJ",
    "reforma tributaria", "nota fiscal eletronica", "CT-e",
    "cooperativa", "floricultura", "DIFAL",
    "substituicao tributaria", "Simples Nacional",
]

# ── Busca no DOU ───────────────────────────────────────────────
def buscar_dou() -> list[dict]:
    resultados = {}
    for termo in TERMOS_DOU:
        for dia in range(7):
            data = data_inicio + timedelta(days=dia)
            if data.weekday() >= 5:  # pula sábado e domingo
                continue
            try:
                api_url = "https://www.in.gov.br/consulta/-/buscar/dou"
                params = {
                    "q":         termo,
                    "s":         "do1",
                    "exactDate": data.strftime("%d-%m-%Y"),
                    "sortType":  0,
                }
                r    = requests.get(api_url, params=params, headers=HEADERS, timeout=15)
                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.select(".resultado-pesquisa, article.resultado, .search-results article")
                for card in cards[:3]:
                    titulo_el = card.select_one("h5, h4, h3, .titulo-ato")
                    link_el   = card.select_one("a")
                    resumo_el = card.select_one("p, .resumo, .conteudo")
                    titulo = titulo_el.get_text(strip=True) if titulo_el else ""
                    link   = link_el["href"] if link_el and link_el.get("href") else ""
                    resumo = resumo_el.get_text(strip=True)[:300] if resumo_el else ""
                    if titulo and titulo not in resultados:
                        if not link.startswith("http"):
                            link = "https://www.in.gov.br" + link
                        resultados[titulo] = {
                            "titulo": titulo,
                            "resumo": resumo,
                            "url":    link,
                            "orgao":  "DOU — Seção 1",
                            "data":   data.strftime("%d/%m/%Y"),
                        }
            except Exception as e:
                print(f"[ERRO DOU] {termo} {data}: {e}")

    items = list(resultados.values())
    items.sort(key=lambda x: x["data"], reverse=True)
    print(f"     {len(items)} itens encontrados no DOU")
    return items[:15]

# ── Receita Federal — RSS ──────────────────────────────────────
def buscar_receita() -> list[dict]:
    kws = ["icms","pis","cofins","ipi","csll","irpj","tributar",
           "cooperativ","reforma","nota fiscal","sped","difal"]
    try:
        feed  = feedparser.parse(
            "https://www.gov.br/receitafederal/pt-br/@@search"
            "?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true"
        )
        items = []
        for e in feed.entries[:50]:
            # Verifica se está dentro da semana
            pub = e.get("published_parsed") or e.get("updated_parsed")
            if pub:
                pub_date = date(*pub[:3])
                if not (data_inicio <= pub_date <= data_fim):
                    continue
            txt = (e.get("title","") + e.get("summary","")).lower()
            if any(k in txt for k in kws):
                items.append({
                    "titulo": e.get("title",""),
                    "resumo": e.get("summary","")[:300],
                    "url":    e.get("link",""),
                    "orgao":  "Receita Federal",
                    "data":   date(*pub[:3]).strftime("%d/%m/%Y") if pub else "—",
                })
        items.sort(key=lambda x: x["data"], reverse=True)
        print(f"     {len(items[:8])} itens encontrados na Receita Federal")
        return items[:8]
    except Exception as ex:
        print(f"[ERRO Receita] {ex}")
        return []

# ── CONFAZ — scraping ──────────────────────────────────────────
def buscar_confaz() -> list[dict]:
    try:
        r    = requests.get(
            "https://www.confaz.fazenda.gov.br/legislacao/convenios",
            headers=HEADERS, timeout=15
        )
        soup = BeautifulSoup(r.text, "html.parser")
        items = []
        for a in soup.select("a")[:80]:
            txt  = a.get_text(strip=True)
            href = a.get("href","")
            if any(k in txt.lower() for k in ["convênio","protocolo","ajuste sinief","ato cotepe"]):
                if len(txt) > 10:
                    link = href if href.startswith("http") else "https://www.confaz.fazenda.gov.br" + href
                    items.append({
                        "titulo": txt,
                        "resumo": "Acesse o ato completo no portal do CONFAZ.",
                        "url":    link,
                        "orgao":  "CONFAZ",
                        "data":   "—",
                    })
            if len(items) >= 8:
                break
        print(f"     {len(items)} itens encontrados no CONFAZ")
        return items
    except Exception as ex:
        print(f"[ERRO CONFAZ] {ex}")
        return []

# ── Montar HTML ────────────────────────────────────────────────
def build_html(dou_items, receita_items, confaz_items) -> str:
    hoje_fmt   = datetime.now().strftime("%d/%m/%Y")
    inicio_fmt = data_inicio.strftime("%d/%m/%Y")
    fim_fmt    = data_fim.strftime("%d/%m/%Y")
    total      = len(dou_items) + len(receita_items) + len(confaz_items)
    link_dou   = f"https://www.in.gov.br/leiturajornal?data={data_fim.strftime('%d-%m-%Y')}&secao=do1"

    def render_items(items):
        if not items:
            return '<p style="color:#999;font-style:italic;">Nenhuma publicação relevante encontrada nesta semana.</p>'
        # Agrupa por data
        por_data = {}
        for it in items:
            d = it.get("data","—")
            por_data.setdefault(d, []).append(it)

        html = ""
        for d in sorted(por_data.keys(), reverse=True):
            html += f'<p style="font-size:12px;font-weight:bold;color:#4a7c3f;margin:12px 0 6px;">📅 {d}</p>'
            for it in por_data[d]:
                html += f"""
                <div style="margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid #eee;">
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
    · DOU: {len(dou_items)} · Receita Federal: {len(receita_items)} · CONFAZ: {len(confaz_items)}<br>
    <a href="{link_dou}" style="color:#1a5276;">🔗 Acessar DOU da semana</a>
  </div>

  <div style="padding:20px 28px;border-bottom:2px solid #4a7c3f;">
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">📋 Diário Oficial da União — Seção 1</h2>
    {render_items(dou_items)}
  </div>

  <div style="padding:20px 28px;border-bottom:2px solid #4a7c3f;">
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">🏛️ Receita Federal — Notícias</h2>
    {render_items(receita_items)}
  </div>

  <div style="padding:20px 28px;">
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">📜 CONFAZ — Atos e Convênios</h2>
    {render_items(confaz_items)}
  </div>

  <div style="background:#f0f0f0;padding:16px 28px;font-size:11px;color:#999;text-align:center;">
    Newsletter gerada automaticamente toda segunda-feira às 10h00 | Cooperflora<br>
    Fontes: Diário Oficial da União · Receita Federal · CONFAZ
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
    print("  → Consultando DOU...")
    dou_items     = buscar_dou()
    print("  → Consultando Receita Federal...")
    receita_items = buscar_receita()
    print("  → Consultando CONFAZ...")
    confaz_items  = buscar_confaz()
    html = build_html(dou_items, receita_items, confaz_items)
    send_newsletter(html)

if __name__ == "__main__":
    main()
