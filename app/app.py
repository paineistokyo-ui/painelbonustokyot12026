# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import json
from pathlib import Path
import unicodedata
import re

# ===================== CONFIG BÁSICA =====================
st.set_page_config(page_title="Painel de Bônus - TOKYO (T4)", layout="wide")
st.title("🚀 Painel de Bônus Trimestral - TOKYO")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# ===================== HELPERS =====================
def norm_txt(s: str) -> str:
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
    k = up(item)
    return ("PRODU" in k) or ("PRD" in k) or k.startswith("PROD")

def extrair_cidade_do_item(item: str, cidades_norm: list) -> str | None:
    k = up(item)
    for c in cidades_norm:
        if c and c in k:
            return c
    return None

# ===================== PARÂMETROS =====================
QUALIDADE_GESTAO_METODO = "por_cidade"
META_ERROS_TOTAIS_GESTAO = 0.035
META_ERROS_GG_GESTAO = 0.015

# ===================== MAPA DE RESPONSABILIDADE =====================
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

_GERENTES_CIDADES_RAW = {
    # ajuste estes nomes/cidades conforme sua operação quando houver gerente no arquivo
    "LEONARDO DE SOUZA": {
        "SANTA INÊS": 1/5,
        "SÃO JOSÉ DE RIBAMAR": 1/5,
        "CHAPADINHA": 1/5,
        "BARRA DO CORDA": 1/5,
        "SÃO JOÃO DOS PATOS": 1/5
    }
}

SUPERVISORES_CIDADES = {
    norm_txt(nome): {norm_txt(cidade): float(peso) for cidade, peso in cidades.items()}
    for nome, cidades in _SUPERVISORES_CIDADES_RAW.items()
}

GERENTES_CIDADES = {
    norm_txt(nome): {norm_txt(cidade): float(peso) for cidade, peso in cidades.items()}
    for nome, cidades in _GERENTES_CIDADES_RAW.items()
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
ORDEM_MESES = ["JANEIRO", "FEVEREIRO", "MARÇO"]
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

# ===================== REGRAS QUALIDADE VISTORIADOR =====================
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

# ===================== REGRAS QUALIDADE GESTÃO =====================
def calc_qualidade_gestao(
    cidades_resp: list,
    total_por_cidade: dict,
    gg_por_cidade: dict,
    meta_total: float = META_ERROS_TOTAIS_GESTAO,
    meta_gg: float = META_ERROS_GG_GESTAO,
    metodo: str = QUALIDADE_GESTAO_METODO
):
    detalhes = []

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

    if not cidades_total and not cidades_gg:
        return 0.0, 0.0, ["Qualidade (gestão) — sem dados por cidade no JSON do mês"]

    if cidades_total:
        ok_total = [c for c in cidades_total if float(total_por_cidade[c]) <= meta_total]
        nok_total = [c for c in cidades_total if c not in ok_total]
        frac_total = len(ok_total) / len(cidades_total)
        if nok_total:
            detalhes.append("Qualidade — Erros Totais (não bateu): " + ", ".join([c.title() for c in nok_total]))
    else:
        frac_total = 0.0
        detalhes.append("Qualidade — Erros Totais: sem dados por cidade")

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

# ===================== CHAVES DA REGRA DE 2 MESES =====================
def pessoa_key(row):
    return (
        up(row.get("NOME", "")),
        up(row.get("FUNÇÃO", "")),
        up(row.get("CIDADE", ""))
    )

def make_loss_entry(ind_key, label, parcela, perdeu, detalhe=""):
    return {
        "key": ind_key,
        "label": label,
        "parcela": float(parcela),
        "perdeu": bool(perdeu),
        "detalhe": detalhe or ""
    }

def cidades_responsabilidade(nome: str, func: str, cidade_padrao: str = "", cidades_disponiveis=None):
    nome_n = up(nome)
    func_n = up(func)
    cidade_n = up(cidade_padrao)

    if func_n == up("SUPERVISOR") and nome_n in SUPERVISORES_CIDADES:
        return SUPERVISORES_CIDADES[nome_n]

    if func_n == up("GERENTE") and nome_n in GERENTES_CIDADES:
        return GERENTES_CIDADES[nome_n]

    if cidade_n:
        return {cidade_n: 1.0}

    cidades_disponiveis = cidades_disponiveis or []
    if cidades_disponiveis:
        peso = 1 / len(cidades_disponiveis)
        return {c: peso for c in cidades_disponiveis}

    return {}

# ===================== AVALIAÇÃO DOS INDICADORES DO MÊS =====================
def avaliar_indicadores_mes(row, nome_mes):
    ind_mes_raw = INDICADORES[nome_mes]

    ind_flags = {
        up(k): v for k, v in ind_mes_raw.items()
        if k not in ["producao_por_cidade", "qualidade_total_por_cidade", "qualidade_gg_por_cidade"]
    }
    prod_cid_norm = {up(k): bool(v) for k, v in ind_mes_raw.get("producao_por_cidade", {}).items()}
    qual_total_cid_norm = {up(k): pct_safe(v) for k, v in ind_mes_raw.get("qualidade_total_por_cidade", {}).items()}
    qual_gg_cid_norm = {up(k): pct_safe(v) for k, v in ind_mes_raw.get("qualidade_gg_por_cidade", {}).items()}

    def flag(chave: str, default=True):
        return ind_flags.get(up(chave), default)

    func = up(row.get("FUNÇÃO", ""))
    cidade = up(row.get("CIDADE", ""))
    nome = up(row.get("NOME", ""))
    obs = row.get("OBSERVAÇÃO", "")
    valor_meta = row.get("VALOR MENSAL META", 0)

    ok, motivo = elegivel(valor_meta, obs)
    if not ok:
        return {
            "MES": nome_mes,
            "META": 0.0,
            "RECEBIDO": 0.0,
            "PERDA": 0.0,
            "%": 0.0,
            "_badge": motivo,
            "_obs": texto_obs(obs),
            "perdeu_itens": [],
            "_entries": []
        }

    metainfo = PESOS.get(func, PESOS.get(row.get("FUNÇÃO", ""), {}))
    total_func = float(metainfo.get("total", valor_meta if pd.notna(valor_meta) else 0))
    itens = metainfo.get("metas", {})
    entries = []

    for item, peso in itens.items():
        parcela = total_func * float(peso)
        item_norm = up(item)

        # ------------------- PRODUÇÃO -------------------
        if is_producao_item(item):
            cid_no_item = extrair_cidade_do_item(item, list(prod_cid_norm.keys()))
            if cid_no_item:
                bateu = prod_cid_norm.get(cid_no_item, True)
                entries.append(make_loss_entry(
                    ind_key=f"PRODUCAO::{cid_no_item}",
                    label=f"Produção – {cid_no_item.title()}",
                    parcela=parcela,
                    perdeu=not bateu
                ))
                continue

            mapa_resp = cidades_responsabilidade(
                nome=nome,
                func=func,
                cidade_padrao=cidade,
                cidades_disponiveis=list(prod_cid_norm.keys())
            )

            if mapa_resp:
                soma_pesos = sum(mapa_resp.values()) or 1.0
                for cid_norm, w in mapa_resp.items():
                    bateu = prod_cid_norm.get(cid_norm, True)
                    fatia = parcela * (float(w) / soma_pesos)
                    entries.append(make_loss_entry(
                        ind_key=f"PRODUCAO::{cid_norm}",
                        label=f"Produção – {cid_norm.title()}",
                        parcela=fatia,
                        perdeu=not bateu
                    ))
                continue

            bateu_prod = prod_cid_norm.get(cidade, True)
            cidade_legivel = str(row.get("CIDADE", "")).title() if row.get("CIDADE", "") else "Cidade não informada"
            entries.append(make_loss_entry(
                ind_key=f"PRODUCAO::{cidade}",
                label=f"Produção – {cidade_legivel}",
                parcela=parcela,
                perdeu=not bateu_prod
            ))
            continue

        # ------------------- QUALIDADE -------------------
        if item_norm == up("QUALIDADE"):
            # VISTORIADOR: divide a parcela de qualidade em 50% total e 50% gg
            if func == up("VISTORIADOR"):
                metade = parcela * 0.5
                et_frac = pct_safe(row.get("ERROS TOTAL", 0))
                eg_frac = pct_safe(row.get("ERROS GG", 0))
                lim_total, lim_graves = limites_qualidade(row.get("CIDADE", ""))

                perdeu_total = et_frac > float(lim_total)
                perdeu_gg = eg_frac > float(lim_graves)

                detalhe_total = f"Erros Totais {fmt_pct(et_frac)} (meta {fmt_pct(lim_total)})"
                detalhe_gg = f"Erros GG {fmt_pct(eg_frac)} (meta {fmt_pct(lim_graves)})"

                entries.append(make_loss_entry(
                    ind_key=f"QUALIDADE_TOTAL::{cidade}",
                    label="Qualidade – Erros Totais",
                    parcela=metade,
                    perdeu=perdeu_total,
                    detalhe=detalhe_total if perdeu_total else ""
                ))
                entries.append(make_loss_entry(
                    ind_key=f"QUALIDADE_GG::{cidade}",
                    label="Qualidade – Erros Graves e Gravíssimos",
                    parcela=metade,
                    perdeu=perdeu_gg,
                    detalhe=detalhe_gg if perdeu_gg else ""
                ))
                continue

            # SUPERVISOR / GERENTE: rateio por cidade de responsabilidade
            if func in [up("SUPERVISOR"), up("GERENTE")]:
                mapa_resp = cidades_responsabilidade(
                    nome=nome,
                    func=func,
                    cidade_padrao=cidade,
                    cidades_disponiveis=list(qual_total_cid_norm.keys())
                )

                metade = parcela * 0.5
                soma_pesos = sum(mapa_resp.values()) or 1.0

                for cid_resp, peso_resp in mapa_resp.items():
                    parcela_cidade = float(peso_resp) / soma_pesos

                    val_total = qual_total_cid_norm.get(cid_resp)
                    val_gg = qual_gg_cid_norm.get(cid_resp)

                    perdeu_total = True if val_total is None else float(val_total) > META_ERROS_TOTAIS_GESTAO
                    perdeu_gg = True if val_gg is None else float(val_gg) > META_ERROS_GG_GESTAO

                    entries.append(make_loss_entry(
                        ind_key=f"QUALIDADE_TOTAL::{cid_resp}",
                        label=f"Qualidade – Erros Totais – {cid_resp.title()}",
                        parcela=metade * parcela_cidade,
                        perdeu=perdeu_total,
                        detalhe=f"Erros Totais {fmt_pct(val_total)} (meta {fmt_pct(META_ERROS_TOTAIS_GESTAO)})" if perdeu_total and val_total is not None else ""
                    ))
                    entries.append(make_loss_entry(
                        ind_key=f"QUALIDADE_GG::{cid_resp}",
                        label=f"Qualidade – Erros Graves e Gravíssimos – {cid_resp.title()}",
                        parcela=metade * parcela_cidade,
                        perdeu=perdeu_gg,
                        detalhe=f"Erros GG {fmt_pct(val_gg)} (meta {fmt_pct(META_ERROS_GG_GESTAO)})" if perdeu_gg and val_gg is not None else ""
                    ))
                continue

            if flag("qualidade", True):
                entries.append(make_loss_entry(
                    ind_key="QUALIDADE_EMPRESA",
                    label="Qualidade",
                    parcela=parcela,
                    perdeu=False
                ))
            else:
                entries.append(make_loss_entry(
                    ind_key="QUALIDADE_EMPRESA",
                    label="Qualidade",
                    parcela=parcela,
                    perdeu=True
                ))
            continue

        # ------------------- LUCRATIVIDADE -------------------
        if item_norm == up("LUCRATIVIDADE"):
            perdeu = not flag("financeiro", True)
            entries.append(make_loss_entry(
                ind_key="LUCRATIVIDADE",
                label="Lucratividade",
                parcela=parcela,
                perdeu=perdeu
            ))
            continue

        # ------------------- ORGANIZAÇÃO DA LOJA -------------------
        if is_org_loja(item):
            perdeu = not flag("organizacao_da_loja", True)
            entries.append(make_loss_entry(
                ind_key="ORGANIZACAO_DA_LOJA",
                label="Organização da Loja 5s",
                parcela=parcela,
                perdeu=perdeu
            ))
            continue

        # ------------------- LIDERANÇA & ORGANIZAÇÃO -------------------
        if is_lider_org(item):
            perdeu = not flag("LIDERANCA_E_ORGANIZACAO", True)
            entries.append(make_loss_entry(
                ind_key="LIDERANCA_E_ORGANIZACAO",
                label="Liderança & Organização",
                parcela=parcela,
                perdeu=perdeu
            ))
            continue

        # ------------------- DEMAIS METAS -------------------
        entries.append(make_loss_entry(
            ind_key=f"OUTRO::{item_norm}",
            label=str(item),
            parcela=parcela,
            perdeu=False
        ))

    perdeu_itens = []
    recebido = 0.0
    perdas = 0.0

    for ent in entries:
        if ent["perdeu"]:
            perdas += ent["parcela"]
            txt = ent["label"]
            if ent["detalhe"]:
                txt += f" — {ent['detalhe']}"
            perdeu_itens.append(txt)
        else:
            recebido += ent["parcela"]

    meta = total_func
    perc = 0.0 if meta == 0 else (recebido / meta) * 100.0

    return {
        "MES": nome_mes,
        "META": meta,
        "RECEBIDO": recebido,
        "PERDA": perdas,
        "%": perc,
        "_badge": "",
        "_obs": texto_obs(obs),
        "perdeu_itens": perdeu_itens,
        "_entries": entries
    }

# ===================== REGRA DO 3º MÊS =====================
def aplicar_regra_dois_meses(df_mes: pd.DataFrame, nome_mes: str, historico_streak: dict) -> pd.DataFrame:
    linhas = []

    for _, row in df_mes.iterrows():
        base = avaliar_indicadores_mes(row, nome_mes)
        pk = pessoa_key(row)

        if base["_badge"]:
            linhas.append(pd.concat([row, pd.Series(base)]))
            continue

        streak_pessoa = historico_streak.setdefault(pk, {})
        perdeu_itens = []
        recebido = 0.0
        perdas = 0.0
        entries_final = []

        for ent in base["_entries"]:
            chave_ind = ent["key"]
            streak_anterior = streak_pessoa.get(chave_ind, 0)

            auto_perda = (streak_anterior >= 2)
            perdeu_final = ent["perdeu"] or auto_perda

            ent_final = ent.copy()
            ent_final["perdeu"] = perdeu_final
            entries_final.append(ent_final)

            if perdeu_final:
                perdas += ent["parcela"]
                if auto_perda and not ent["perdeu"]:
                    perdeu_itens.append(f"{ent['label']} — perda automática no 3º mês por 2 meses consecutivos")
                else:
                    txt = ent["label"]
                    if ent["detalhe"]:
                        txt += f" — {ent['detalhe']}"
                    perdeu_itens.append(txt)
            else:
                recebido += ent["parcela"]

            streak_pessoa[chave_ind] = streak_anterior + 1 if perdeu_final else 0

        meta = base["META"]
        perc = 0.0 if meta == 0 else (recebido / meta) * 100.0

        final = {
            "MES": nome_mes,
            "META": meta,
            "RECEBIDO": recebido,
            "PERDA": perdas,
            "%": perc,
            "_badge": base["_badge"],
            "_obs": base["_obs"],
            "perdeu_itens": perdeu_itens,
            "_entries": entries_final
        }

        linhas.append(pd.concat([row, pd.Series(final)]))

    return pd.DataFrame(linhas)

def calcular_meses_sequenciais(meses_dfs: dict) -> pd.DataFrame:
    historico_streak = {}
    partes = []

    for mes in ORDEM_MESES:
        df_mes = meses_dfs[mes].copy()
        calc_mes = aplicar_regra_dois_meses(df_mes, mes, historico_streak)
        partes.append(calc_mes)

    return pd.concat(partes, ignore_index=True)

# ===================== LEITURA / CÁLCULO =====================
try:
    meses_dfs = {mes: ler_planilha(mes) for mes in ORDEM_MESES}
    st.success("✅ Planilhas carregadas com sucesso: JANEIRO, FEVEREIRO e MARÇO!")
except Exception as e:
    st.error(f"Erro ao ler a planilha: {e}")
    st.stop()

dados_full = calcular_meses_sequenciais(meses_dfs)

if filtro_mes == "TRIMESTRE":
    group_cols = ["CIDADE", "NOME", "FUNÇÃO", "DATA DE ADMISSÃO", "TEMPO DE CASA"]
    agg = (
        dados_full
        .groupby(group_cols, dropna=False)
        .agg({
            "META": "sum",
            "RECEBIDO": "sum",
            "PERDA": "sum",
            "_obs": lambda x: ", ".join(sorted({s for s in x if s})),
            "_badge": lambda x: " / ".join(sorted({s for s in x if s}))
        })
        .reset_index()
    )

    agg["%"] = agg.apply(
        lambda r: 0.0 if r["META"] == 0 else (r["RECEBIDO"] / r["META"]) * 100.0,
        axis=1
    )

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
    dados_calc = dados_full[dados_full["MES"] == filtro_mes].copy()
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
        if perdidos_txt:
            st.caption(f"🔻 Indicadores não entregues: {perdidos_txt}")
