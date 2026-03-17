# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import json
from pathlib import Path
import unicodedata, re

# ===================== CONFIG BÁSICA =====================
st.set_page_config(page_title="Painel de Bônus - TOKYO (T4)", layout="wide")
st.title("🚀 Painel de Bônus Trimestral - TOKYO")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# ===================== HELPERS (TEXTO / % / VARIAÇÕES) =====================
def norm_txt(s: str) -> str:
    """UPPER + remove acentos + colapsa espaços internos."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s).strip().upper()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

def up(s):
    return norm_txt(s)

def texto_obs(valor):
    if pd.isna(valor):
        return ""
    s = str(valor).strip()
    return "" if s.lower() in ["none", "nan", ""] else s

def int_safe(x):
    try:
        return int(float(x))
    except Exception:
        return 0

def pct_safe(x):
    """Converte valor de % do Excel para fração (0-1). Aceita 0.035 ou 3.5."""
    try:
        x = float(x)
        if x > 1:
            return x / 100.0
        return x
    except Exception:
        return 0.0

def fmt_pct(x):
    try:
        return f"{float(x) * 100:.2f}%"
    except Exception:
        return "0.00%"

def is_org_loja(item: str) -> bool:
    k = norm_txt(item)
    return "ORGANIZACAO DA LOJA" in k

def is_lider_org(item: str) -> bool:
    k = norm_txt(item)
    return ("LIDERANCA" in k) and ("ORGANIZACAO" in k)

def is_producao_item(item: str) -> bool:
    """
    Detecta itens de Produção mesmo com variações:
    PRODUÇÃO / PRODUCAO / PRDÇÃO / PRDCAO / PRD / PROD.
    """
    k = up(item)
    return ("PRODU" in k) or ("PRD" in k) or k.startswith("PROD")

def extrair_cidade_do_item(item: str, cidades_norm: list) -> str | None:
    """Acha a cidade dentro do texto do item (ex: 'PRDÇÃO SÃO LUIS')."""
    k = up(item)
    for c in cidades_norm:
        if c and c in k:
            return c
    return None

# ===================== PARÂMETROS (QUALIDADE GESTÃO) =====================
# Ajustado para o seu cenário: Qualidade da gestão por CIDADE (proporção de cidades que bateram)
QUALIDADE_GESTAO_METODO = "por_cidade"

META_ERROS_TOTAIS_GESTAO = 0.035  # 3,5%
META_ERROS_GG_GESTAO = 0.015      # 1,5%

# ===================== MAPA DE RESPONSABILIDADE (RATEIO PRODUÇÃO) =====================
# Aqui é usado APENAS quando o item de produção for "genérico" (sem cidade no nome).
# Se no PESOS já tiver "PRDÇÃO SÃO LUIS 8%" etc, o código usa o item e ignora este rateio.
_SUPERVISORES_CIDADES_RAW = {
    "ANTÔNIO FRANCISCO DE CARVALHO FERREIRA": {
        "SANTA INÊS": 1/3,
        "SÃO JOÃO DOS PATOS": 1/3,
        "BARRA DO CORDA": 1/3
    },
    "MADSON RONNY PEREIRA MELO": {
        "CHAPADINHA": 1/2,
        "SÃO JOSÉ DE RIBAMAR": 1/2
    }
}
SUPERVISORES_CIDADES = {
    norm_txt(nome): {norm_txt(cidade): float(peso) for cidade, peso in cidades.items()}
    for nome, cidades in _SUPERVISORES_CIDADES_RAW.items()
}

# ===================== CARREGAMENTO ======================
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

try:
    PESOS = load_json(DATA_DIR / "pesos_tokyo.json")
    INDICADORES = load_json(DATA_DIR / "empresa_indicadores_tokyo.json")
except Exception as e:
    st.error(f"Erro ao carregar JSONs: {e}")
    st.stop()

MESES = ["TRIMESTRE", "JANEIRO", "FEVEREIRO", "MARÇO"]
filtro_mes = st.radio("📅 Selecione o mês:", MESES, horizontal=True)

def ler_planilha(mes: str) -> pd.DataFrame:
    base = DATA_DIR / "RESUMO PARA PAINEL - TOKYO.xlsx"
    if base.exists():
        return pd.read_excel(base, sheet_name=mes)
    candidatos = list(DATA_DIR.glob("RESUMO PARA PAINEL - TOKYO*.xls*"))
    if not candidatos:
        st.error("Planilha não encontrada na pasta data/ (RESUMO PARA PAINEL - TOKYO.xlsx)")
        st.stop()
    return pd.read_excel(sorted(candidatos)[0], sheet_name=mes)

# ===================== REGRAS (QUALIDADE VISTORIADOR) =====================
LIMITES_QUALIDADE_POR_CIDADE = {
    up("SANTA INÊS"): {"total": 0.035, "graves": 0.015},
    up("SÃO JOÃO DOS PATOS"): {"total": 0.035, "graves": 0.015},
    up("BARRA DO CORDA"): {"total": 0.035, "graves": 0.015},
    up("CHAPADINHA"): {"total": 0.035, "graves": 0.015},
    up("SÃO JOSÉ DE RIBAMAR"): {"total": 0.035, "graves": 0.015},
}
LIMITE_TOTAL_PADRAO = 0.035
LIMITE_GRAVES_PADRAO = 0.015

def limites_qualidade(cidade: str):
    c = up(cidade)
    cfg = LIMITES_QUALIDADE_POR_CIDADE.get(c)
    if cfg:
        return float(cfg["total"]), float(cfg["graves"])
    return LIMITE_TOTAL_PADRAO, LIMITE_GRAVES_PADRAO

def pct_qualidade_vistoriador(erros_total_frac: float, erros_graves_frac: float, limite_total: float, limite_graves: float) -> float:
    et = 0.0 if pd.isna(erros_total_frac) else float(erros_total_frac)
    eg = 0.0 if pd.isna(erros_graves_frac) else float(erros_graves_frac)

    total_ok = et <= float(limite_total)
    graves_ok = eg <= float(limite_graves)

    if total_ok and graves_ok:
        return 1.0
    if (not total_ok and graves_ok) or (total_ok and not graves_ok):
        return 0.5
    return 0.0

# ===================== REGRAS (QUALIDADE SUPERVISOR/GERENTE) =====================
def calc_qualidade_gestao(cidades_resp: list,
                          total_por_cidade: dict,
                          gg_por_cidade: dict,
                          meta_total: float = META_ERROS_TOTAIS_GESTAO,
                          meta_gg: float = META_ERROS_GG_GESTAO,
                          metodo: str = QUALIDADE_GESTAO_METODO):
    detalhes = []

    # garante só cidades que existem no JSON do mês
    cidades_total = [c for c in cidades_resp if c in total_por_cidade]
    cidades_gg = [c for c in cidades_resp if c in gg_por_cidade]

    if metodo == "media_simples":
        vals_total = [float(total_por_cidade[c]) for c in cidades_total]
        vals_gg = [float(gg_por_cidade[c]) for c in cidades_gg]
        if not vals_total and not vals_gg:
            return 0.0, 0.0, ["Qualidade (gestão) — sem dados por cidade no JSON do mês"]

        avg_total = (sum(vals_total) / len(vals_total)) if vals_total else None
        avg_gg = (sum(vals_gg) / len(vals_gg)) if vals_gg else None

        frac_total = 1.0 if (avg_total is not None and avg_total <= meta_total) else 0.0
        frac_gg = 1.0 if (avg_gg is not None and avg_gg <= meta_gg) else 0.0

        if frac_total < 1.0:
            detalhes.append(f"Qualidade — Erros Totais: média {fmt_pct(avg_total)} (meta {fmt_pct(meta_total)})")
        if frac_gg < 1.0:
            detalhes.append(f"Qualidade — Erros GG: média {fmt_pct(avg_gg)} (meta {fmt_pct(meta_gg)})")

        return frac_total, frac_gg, detalhes

    # por_cidade
    if not cidades_total and not cidades_gg:
        return 0.0, 0.0, ["Qualidade (gestão) — sem dados por cidade no JSON do mês"]

    # totais
    if cidades_total:
        ok_total = [c for c in cidades_total if float(total_por_cidade[c]) <= meta_total]
        nok_total = [c for c in cidades_total if c not in ok_total]
        frac_total = len(ok_total) / len(cidades_total)
        if nok_total:
            detalhes.append("Qualidade — Erros Totais (não bateu): " + ", ".join([c.title() for c in nok_total]))
    else:
        frac_total = 0.0
        detalhes.append("Qualidade — Erros Totais: sem dados por cidade")

    # gg
    if cidades_gg:
        ok_gg = [c for c in cidades_gg if float(gg_por_cidade[c]) <= meta_gg]
        nok_gg = [c for c in cidades_gg if c not in ok_gg]
        frac_gg = len(ok_gg) / len(cidades_gg)
        if nok_gg:
            detalhes.append("Qualidade — Erros GG (não bateu): " + ", ".join([c.title() for c in nok_gg]))
    else:
        frac_gg = 0.0
        detalhes.append("Qualidade — Erros GG: sem dados por cidade")

    return float(frac_total), float(frac_gg), detalhes

def elegivel(valor_meta, obs):
    obs_u = up(obs)
    if pd.isna(valor_meta) or float(valor_meta) == 0:
        return False, "Sem elegibilidade no mês"
    if "LICEN" in obs_u:
        return False, "Licença no mês"
    return True, ""

# ===================== CÁLCULO (POR MÊS) =====================
def calcula_mes(df_mes: pd.DataFrame, nome_mes: str) -> pd.DataFrame:
    ind_mes_raw = INDICADORES[nome_mes]

    # flags e produção por cidade (boolean de bateu)
    ind_flags = {up(k): v for k, v in ind_mes_raw.items() if k != "producao_por_cidade"}
    prod_cid_norm = {up(k): bool(v) for k, v in ind_mes_raw.get("producao_por_cidade", {}).items()}

    # qualidade por cidade (percentuais)
    qual_total_cid_norm = {up(k): pct_safe(v) for k, v in ind_mes_raw.get("qualidade_total_por_cidade", {}).items()}
    qual_gg_cid_norm = {up(k): pct_safe(v) for k, v in ind_mes_raw.get("qualidade_gg_por_cidade", {}).items()}

    def flag(chave: str, default=True):
        return ind_flags.get(up(chave), default)

    df = df_mes.copy()

    def calcula_recebido(row):
        func = up(row.get("FUNÇÃO", ""))
        cidade = up(row.get("CIDADE", ""))
        nome = up(row.get("NOME", ""))
        obs = row.get("OBSERVAÇÃO", "")
        valor_meta = row.get("VALOR MENSAL META", 0)

        ok, motivo = elegivel(valor_meta, obs)
        perdeu_itens = []

        if not ok:
            return pd.Series({
                "MES": nome_mes, "META": 0.0, "RECEBIDO": 0.0, "PERDA": 0.0, "%": 0.0,
                "_badge": motivo, "_obs": texto_obs(obs), "perdeu_itens": perdeu_itens
            })

        metainfo = PESOS.get(func, PESOS.get(row.get("FUNÇÃO", ""), {}))
        total_func = float(metainfo.get("total", valor_meta if pd.notna(valor_meta) else 0))
        itens = metainfo.get("metas", {})

        recebido, perdas = 0.0, 0.0

        for item, peso in itens.items():
            parcela = total_func * float(peso)
            item_norm = up(item)

            # ------------------- PRODUÇÃO -------------------
            if is_producao_item(item):
                # Se o PESOS já tem a cidade no nome (ex: "PRDÇÃO SÃO LUIS 8%"), calcula direto.
                cid_no_item = extrair_cidade_do_item(item, list(prod_cid_norm.keys()))
                if cid_no_item:
                    bateu = prod_cid_norm.get(cid_no_item, True)
                    if bateu:
                        recebido += parcela
                    else:
                        perdas += parcela
                        perdeu_itens.append("Produção – " + cid_no_item.title())
                    continue

                # Se não tem cidade no item, usa rateio por responsabilidade
                if func in [up("SUPERVISOR"), up("GERENTE")] and nome in SUPERVISORES_CIDADES:
                    perdas_cids = []
                    base_soma = sum(SUPERVISORES_CIDADES[nome].values()) or 1.0

                    for cid_norm, w in SUPERVISORES_CIDADES[nome].items():
                        bateu = prod_cid_norm.get(cid_norm, True)
                        fatia = parcela * (float(w) / base_soma)

                        if bateu:
                            recebido += fatia
                        else:
                            perdas += fatia
                            perdas_cids.append(cid_norm.title())

                    if perdas_cids:
                        perdeu_itens.append("Produção – " + ", ".join(perdas_cids))
                    continue

                # fallback: usa cidade do colaborador
                bateu_prod = prod_cid_norm.get(cidade, True)
                if bateu_prod:
                    recebido += parcela
                else:
                    perdas += parcela
                    cidade_legivel = (str(row.get("CIDADE", "")).title() if row.get("CIDADE", "") else "Cidade não informada")
                    perdeu_itens.append("Produção – " + cidade_legivel)
                continue

            # ------------------- QUALIDADE -------------------
            if item_norm == up("Qualidade"):
                # Vistoriador: 0/50/100 por limites da cidade
                if func == up("VISTORIADOR"):
                    et_frac = pct_safe(row.get("ERROS TOTAL", 0))
                    eg_frac = pct_safe(row.get("ERROS GG", 0))

                    lim_total, lim_graves = limites_qualidade(row.get("CIDADE", ""))
                    frac = pct_qualidade_vistoriador(et_frac, eg_frac, lim_total, lim_graves)

                    if frac == 1.0:
                        recebido += parcela
                    elif frac == 0.5:
                        recebido += parcela * 0.5
                        perdas += parcela * 0.5
                        perdeu_itens.append(
                            f"Qualidade (50%) — total {fmt_pct(et_frac)} | graves {fmt_pct(eg_frac)} "
                            f"(meta: {fmt_pct(lim_total)} / {fmt_pct(lim_graves)})"
                        )
                    else:
                        perdas += parcela
                        perdeu_itens.append(
                            f"Qualidade (0%) — total {fmt_pct(et_frac)} | graves {fmt_pct(eg_frac)} "
                            f"(meta: {fmt_pct(lim_total)} / {fmt_pct(lim_graves)})"
                        )
                    continue

                # Supervisor/Gerente: 20% dividido em 10% totais + 10% gg, por cidade
                if func in [up("SUPERVISOR"), up("GERENTE")]:
                    cidades_resp = list(SUPERVISORES_CIDADES.get(nome, {}).keys())
                    if not cidades_resp:
                        # fallback: tenta todas do JSON, ou a cidade do colaborador
                        cidades_resp = list(qual_total_cid_norm.keys()) or ([cidade] if cidade else [])

                    frac_total, frac_gg, detalhes = calc_qualidade_gestao(
                        cidades_resp=cidades_resp,
                        total_por_cidade=qual_total_cid_norm,
                        gg_por_cidade=qual_gg_cid_norm,
                        meta_total=META_ERROS_TOTAIS_GESTAO,
                        meta_gg=META_ERROS_GG_GESTAO,
                        metodo=QUALIDADE_GESTAO_METODO
                    )

                    metade = parcela * 0.5  # 10% + 10%
                    recebido += metade * float(frac_total)
                    perdas += metade * (1.0 - float(frac_total))

                    recebido += metade * float(frac_gg)
                    perdas += metade * (1.0 - float(frac_gg))

                    if float(frac_total) < 1.0 or float(frac_gg) < 1.0:
                        perdeu_itens.append("Qualidade (gestão)")
                        perdeu_itens.extend(detalhes)

                    continue

                # Outras funções: empresa-wide
                if flag("qualidade", True):
                    recebido += parcela
                else:
                    perdas += parcela
                    perdeu_itens.append("Qualidade")
                continue

            # ------------------- LUCRATIVIDADE -------------------
            if item_norm == up("Lucratividade"):
                if flag("financeiro", True):
                    recebido += parcela
                else:
                    perdas += parcela
                    perdeu_itens.append("Lucratividade")
                continue

            # ------------------- ORGANIZAÇÃO DA LOJA -------------------
            if is_org_loja(item):
                if flag("organizacao_da_loja", True):
                    recebido += parcela
                else:
                    perdas += parcela
                    perdeu_itens.append("Organização da Loja 5s")
                continue

            # ------------------- LIDERANÇA & ORGANIZAÇÃO -------------------
            if is_lider_org(item):
                if flag("Liderança & Organização", True):
                    recebido += parcela
                else:
                    perdas += parcela
                    perdeu_itens.append("Liderança & Organização")
                continue

            # ------------------- DEMAIS METAS: CONSIDERA BATIDAS -------------------
            recebido += parcela

        meta = total_func
        perc = 0.0 if meta == 0 else (recebido / meta) * 100.0

        return pd.Series({
            "MES": nome_mes, "META": meta, "RECEBIDO": recebido, "PERDA": perdas,
            "%": perc, "_badge": "", "_obs": texto_obs(obs), "perdeu_itens": perdeu_itens
        })

    calc = df.apply(calcula_recebido, axis=1)
    return pd.concat([df.reset_index(drop=True), calc], axis=1)

# ===================== LEITURA (TRIMESTRE OU MÊS) =====================
if filtro_mes == "TRIMESTRE":
    try:
        df_o, df_n, df_d = [ler_planilha(m) for m in ["JANEIRO", "FEVEREIRO", "MARÇO"]]
        st.success("✅ Planilhas carregadas com sucesso: JANEIRO, FEVEREIRO e MARÇO!")
    except Exception as e:
        st.error(f"Erro ao ler a planilha: {e}")
        st.stop()

    dados_full = pd.concat([
        calcula_mes(df_o, "JANEIRO"),
        calcula_mes(df_n, "FEVEREIRO"),
        calcula_mes(df_d, "MARÇO")
    ], ignore_index=True)

    group_cols = ["CIDADE", "NOME", "FUNÇÃO", "DATA DE ADMISSÃO", "TEMPO DE CASA"]
    agg = (dados_full
           .groupby(group_cols, dropna=False)
           .agg({
               "META": "sum",
               "RECEBIDO": "sum",
               "PERDA": "sum",
               "_obs": lambda x: ", ".join(sorted({s for s in x if s})),
               "_badge": lambda x: " / ".join(sorted({s for s in x if s}))
           })
           .reset_index())

    agg["%"] = agg.apply(lambda r: 0.0 if r["META"] == 0 else (r["RECEBIDO"] / r["META"]) * 100.0, axis=1)

    perdas_pessoa = (
        dados_full.assign(_lost=lambda d: d.apply(
            lambda r: [f"{it} ({r['MES']})" for it in r["perdeu_itens"]],
            axis=1))
        .groupby(group_cols, dropna=False)["_lost"]
        .sum()
        .apply(lambda L: ", ".join(sorted(set(L))))
        .reset_index()
        .rename(columns={"_lost": "INDICADORES_NAO_ENTREGUES"})
    )

    dados_calc = agg.merge(perdas_pessoa, on=group_cols, how="left")
    dados_calc["INDICADORES_NAO_ENTREGUES"] = dados_calc["INDICADORES_NAO_ENTREGUES"].fillna("")
else:
    try:
        df_mes = ler_planilha(filtro_mes)
        st.success(f"✅ Planilha de {filtro_mes} carregada!")
    except Exception as e:
        st.error(f"Erro ao ler a planilha: {e}")
        st.stop()

    dados_calc = calcula_mes(df_mes, filtro_mes)
    dados_calc["INDICADORES_NAO_ENTREGUES"] = dados_calc["perdeu_itens"].apply(
        lambda L: ", ".join(L) if isinstance(L, list) and L else ""
    )

# ===================== FILTROS =====================
st.markdown("### 🔎 Filtros")
col1, col2, col3, col4 = st.columns(4)

with col1:
    filtro_nome = st.text_input("Buscar por nome (contém)", "")

with col2:
    funcoes_validas = [f for f in dados_calc["FUNÇÃO"].dropna().unique() if up(f) in PESOS.keys()]
    filtro_funcao = st.selectbox("Função", ["Todas"] + sorted(funcoes_validas))

with col3:
    cidades = ["Todas"] + sorted(dados_calc["CIDADE"].dropna().unique())
    filtro_cidade = st.selectbox("Cidade", cidades)

with col4:
    tempos = ["Todos"] + sorted(dados_calc["TEMPO DE CASA"].dropna().unique())
    filtro_tempo = st.selectbox("Tempo de casa", tempos)

dados_view = dados_calc.copy()
if filtro_nome:
    dados_view = dados_view[dados_view["NOME"].str.contains(filtro_nome, case=False, na=False)]
if filtro_funcao != "Todas":
    dados_view = dados_view[dados_view["FUNÇÃO"] == filtro_funcao]
if filtro_cidade != "Todas":
    dados_view = dados_view[dados_view["CIDADE"] == filtro_cidade]
if filtro_tempo != "Todos":
    dados_view = dados_view[dados_view["TEMPO DE CASA"] == filtro_tempo]

# ===================== RESUMO =====================
st.markdown("### 📊 Resumo Geral")
colA, colB, colC = st.columns(3)
with colA:
    st.success(f"💰 Total possível: R$ {dados_view['META'].sum():,.2f}")
with colB:
    st.info(f"📈 Recebido: R$ {dados_view['RECEBIDO'].sum():,.2f}")
with colC:
    st.error(f"📉 Deixou de ganhar: R$ {dados_view['PERDA'].sum():,.2f}")

# ===================== CARDS =====================
st.markdown("### 👥 Colaboradores")
cols = st.columns(3)

dados_view = dados_view.sort_values(by="%", ascending=False)

for idx, row in dados_view.iterrows():
    pct = float(row["%"]) if pd.notna(row["%"]) else 0.0
    meta = float(row["META"]) if pd.notna(row["META"]) else 0.0
    recebido = float(row["RECEBIDO"]) if pd.notna(row["RECEBIDO"]) else 0.0
    perdido = float(row["PERDA"]) if pd.notna(row["PERDA"]) else 0.0
    badge = row.get("_badge", "")
    obs_txt = texto_obs(row.get("_obs", ""))
    perdidos_txt = texto_obs(row.get("INDICADORES_NAO_ENTREGUES", ""))

    bg = "#f9f9f9" if not badge else "#eeeeee"

    with cols[idx % 3]:
        st.markdown(f"""
        <div style="border:1px solid #ccc;padding:16px;border-radius:12px;margin-bottom:12px;background:{bg}">
            <h4 style="margin:0">{str(row.get('NOME','')).title()}</h4>
            <p style="margin:4px 0;"><strong>{row.get('FUNÇÃO','')}</strong> — {row.get('CIDADE','')}</p>
            <p style="margin:4px 0;">
                <strong>Meta {'Trimestral' if filtro_mes=='TRIMESTRE' else 'Mensal'}:</strong> R$ {meta:,.2f}<br>
                <strong>Recebido:</strong> R$ {recebido:,.2f}<br>
                <strong>Deixou de ganhar:</strong> R$ {perdido:,.2f}<br>
                <strong>Cumprimento:</strong> {pct:.1f}%
            </p>
            <div style="height: 10px; background: #ddd; border-radius: 5px; overflow: hidden;">
                <div style="width: {max(0.0, min(100.0, pct)):.1f}%; background: black; height: 100%;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if badge:
            st.caption(f"⚠️ {badge}")
        if obs_txt:
            st.caption(f"🗒️ {obs_txt}")
        if perdidos_txt and "100%" not in perdidos_txt:
            st.caption(f"🔻 Indicadores não entregues: {perdidos_txt}")

