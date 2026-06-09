import requests
import resend
import os
import feedparser
from datetime import datetime, date, timedelta

# ── Configurações ──────────────────────────────────────────────
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
FROM_EMAIL     = "newsletter@resend.dev"
TO_EMAILS      = ["guilherme.chaves@cooperflora.com.br"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (newsletter-fiscal-cooperflora)",
    "Accept":     "application/json, text/plain, */*",
}

# ── Período: semana anterior (seg a sex) ───────────────────────
hoje        = date.today()
data_inicio = hoje - timedelta(days=7)
data_fim    = hoje - timedelta(days=1)

TERMOS_DOU = [
    "ICMS", "PIS", "COFINS", "IPI", "CSLL", "IRPJ",
    "reforma tributaria", "nota fiscal eletronica", "CT-e",
    "cooperativa", "floricultura", "DIFAL",
    "substituicao tributaria", "Simples Nacional",
]

# ── API oficial DOU (Imprensa Nacional) ────────────────────────
def buscar_dou() -> list[dict]:
    """
    Usa a API interna da Imprensa Nacional — a mesma usada pelo
    buscador oficial em https://www.in.gov.br/consulta/
    Endpoint descoberto via Ro-DOU (ferramenta oficial do governo federal).
    """
    resultados = {}

    for dia in range(7):
        data = data_inicio + timedelta(days=dia)
        if data.weekday() >= 5:
            continue

        data_str = data.strftime("%d-%m-%Y")

        for termo in TERMOS_DOU:
            try:
                url = "https://www.in.gov.br/consulta/-/buscar/dou"
                params = {
                    "q":            termo,
                    "s":            "do1",      # Seção 1 — atos normativos
                    "exactDate":    data_str,
                    "sortType":     0,
                    "delta":        5,
                    "orgPrin":      "",
                    "orgSub":       "",
                    "artType":      "",
                }
                r = requests.get(url, params=params, headers=HEADERS, timeout=20)

                # Tenta JSON (API retorna JSON quando aceito)
                ct = r.headers.get("Content-Type","")
                if "json" in ct:
                    data_json = r.json()
                    hits = data_json.get("content", data_json.get("items", []))
                    for hit in hits[:3]:
                        titulo = hit.get("title", hit.get("titulo",""))
                        resumo = hit.get("content", hit.get("resumo",""))[:300]
                        href   = hit.get("urlTitle", hit.get("url",""))
                        if not href.startswith("http"):
                            href = "https://www.in.gov.br" + href
                        if titulo and titulo not in resultados:
                            resultados[titulo] = {
                                "titulo": titulo,
                                "resumo": resumo,
                                "url":    href,
                                "orgao":  hit.get("artCategory", "DOU — Seção 1"),
                                "data":   data.strftime("%d/%m/%Y"),
                            }
                else:
                    # Fallback: parse HTML com regex simples
                    import re
                    titulos = re.findall(r'class="title-marker[^"]*"[^>]*>([^<]+)<', r.text)
                    links   = re.findall(r'href="(/web/dou/-/[^"]+)"', r.text)
                    for i, t in enumerate(titulos[:3]):
                        t = t.strip()
                        if t and t not in resultados:
                            href = f"https://www.in.gov.br{links[i]}" if i < len(links) else "https://www.in.gov.br/consulta"
                            resultados[t] = {
                                "titulo": t,
                                "resumo": f"Publicado em {data.strftime('%d/%m/%Y')} — acesse o ato completo.",
                                "url":    href,
                                "orgao":  "DOU — Seção 1",
                                "data":   data.strftime("%d/%m/%Y"),
                            }

            except Exception as e:
                print(f"[ERRO DOU] {termo} {data_str}: {e}")

    items = list(resultados.values())
    items.sort(key=lambda x: x["data"], reverse=True)
    print(f"     {len(items)} itens encontrados no DOU")
    return items[:15]

# ── Receita Federal — múltiplos RSS ───────────────────────────
def buscar_receita() -> list[dict]:
    kws = ["icms","pis","cofins","ipi","csll","irpj","tributar",
           "cooperativ","reforma","nota fiscal","sped","difal",
           "obrigacao acessoria","instrucao normativa"]
    feeds_urls = [
        "https://www.gov.br/receitafederal/pt-br/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true",
        "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true",
    ]
    items = []
    vistos = set()
    for url in feeds_urls:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
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
                        items.append({
                            "titulo": titulo,
                            "resumo": e.get("summary","")[:300],
                            "url":    e.get("link",""),
                            "orgao":  "Receita Federal",
                            "data":   date(*pub[:3]).strftime("%d/%m/%Y") if pub else "—",
                        })
        except Exception as ex:
            print(f"[ERRO Receita RSS] {ex}")

    items.sort(key=lambda x: x["data"], reverse=True)
    print(f"     {len(items[:8])} itens encontrados na Receita Federal")
    return items[:8]

# ── CONFAZ — RSS alternativo ───────────────────────────────────
def buscar_confaz() -> list[dict]:
    """Usa RSS do Portal da Fazenda como alternativa ao CONFAZ direto."""
    feeds_urls = [
        "https://www.gov.br/fazenda/pt-br/@@search?portal_type=News+Item&sort_on=effective&sort_order=descending&RSS=true",
    ]
    kws = ["convênio","protocolo","confaz","icms","ajuste sinief","ato cotepe","tributar"]
    items = []
    try:
        for url in feeds_urls:
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
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
                        "orgao":  "CONFAZ / Fazenda",
                        "data":   date(*pub[:3]).strftime("%d/%m/%Y") if pub else "—",
                    })
    except Exception as ex:
        print(f"[ERRO CONFAZ/Fazenda] {ex}")

    items.sort(key=lambda x: x["data"], reverse=True)
    print(f"     {len(items[:5])} itens encontrados no CONFAZ/Fazenda")
    return items[:5]

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

  <div style="background:#e8f5e9;padding:12px 28px;font-size:13px;color:#2e7d32;border-bottom:1px solid #c8e6c9;">
    ✅ <strong>{total} publicações relevantes</strong> encontradas nesta semana
    · DOU: {len(dou_items)} · Receita Federal: {len(receita_items)} · CONFAZ/Fazenda: {len(confaz_items)}<br>
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
    <h2 style="color:#4a7c3f;font-size:15px;border-left:4px solid #4a7c3f;padding-left:10px;">📜 CONFAZ / Fazenda — Atos e Convênios</h2>
    {render_items(confaz_items)}
  </div>

  <div style="background:#f0f0f0;padding:16px 28px;font-size:11px;color:#999;text-align:center;">
    Newsletter gerada automaticamente toda segunda-feira às 10h00 | Cooperflora<br>
    Fontes: Diário Oficial da União · Receita Federal · CONFAZ · Ministério da Fazenda
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
    print("  → Consultando CONFAZ/Fazenda...")
    confaz_items  = buscar_confaz()
    html = build_html(dou_items, receita_items, confaz_items)
    send_newsletter(html)

if __name__ == "__main__":
    main()
