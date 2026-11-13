import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime
import hashlib
import re
from playwright.async_api import async_playwright
import requests

# =====================================================================
# 1. CONFIGURAÇÕES INICIAIS (Parâmetros ajustáveis)
# =====================================================================
ABAS_DO_SITE = [
    (
        "Pijamas_e_Kits",
        "https://www.dafiti.com.br/roupas-masculinas/pijamas-e-kits/",
    ),
    ("Masculino", "https://www.dafiti.com.br/roupas-masculinas/"),
    ("Feminino", "https://www.dafiti.com.br/roupas-femininas/"),
    ("Calcados", "https://www.dafiti.com.br/calcados/"),
    ("Sports", "https://www.dafiti.com.br/esportes/"),
    ("Infantil", "https://www.dafiti.com.br/roupas-infantis/"),
    ("Acessorios", "https://www.dafiti.com.br/acessorios/"),
    ("Outlet", "https://www.dafiti.com.br/outlet/"),
    (
        "Campanha_Black",
        "https://www.dafiti.com.br/promocao/geral/black-tudo-desconto",
    ),
]

# 4 páginas simultâneas evita bloqueios do servidor e garante carregamento completo
PAGINAS_SIMULTANEAS = 4

# Nomes dos ficheiros de saída
ARQUIVO_BASE = "dafiti_base_completa_lida.csv"
ARQUIVO_DUPLICADOS = "dafiti_duplicados_com_motivo.csv"


# =====================================================================
# 2. FUNÇÕES AUXILIARES (Formatação de Tempo, Salvamento e URL)
# =====================================================================
def formatar_duracao(intervalo_tempo):
    """Converte um objeto timedelta (fim - inicio) para o formato HH:MM:SS."""
    total_segundos = int(intervalo_tempo.total_seconds())
    horas, resto = divmod(total_segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def salvar_csv_seguro(nome_arquivo, lista_dados, colunas):
    """Guarda o CSV de forma segura.

    Se o ficheiro estiver aberto no Excel (PermissionError),
    cria uma cópia com data e hora no nome para nunca perder os dados.
    """
    try:
        with open(
            nome_arquivo, mode="w", newline="", encoding="utf-8-sig"
        ) as f:
            escritor = csv.DictWriter(
                f, fieldnames=colunas, delimiter=";", extrasaction="ignore"
            )
            escritor.writeheader()
            escritor.writerows(lista_dados)
        return nome_arquivo
    except PermissionError:
        nome_alt = nome_arquivo.replace(
            ".csv", f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        with open(nome_alt, mode="w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(
                f, fieldnames=colunas, delimiter=";", extrasaction="ignore"
            )
            escritor.writeheader()
            escritor.writerows(lista_dados)
        return nome_alt


def extrair_nome_do_link(url):
    """Extrai o nome completo do produto a partir da URL (evita cortes de '...' na vitrine)."""
    parte_final = url.rstrip("/").split("/")[-1]
    sem_extensao = re.sub(r"\.html$", "", parte_final, flags=re.IGNORECASE)
    sem_sku = re.sub(r"-\d+$", "", sem_extensao)
    return sem_sku.replace("-", " ").lower().strip()


# =====================================================================
# 3. FUNÇÕES DE NAVEGAÇÃO ASSÍNCRONA (VITRINE E PÁGINA INTERNA)
# =====================================================================
async def ler_pagina_vitrine(
    aba_browser, nome_aba, url_aba, num_pagina, detectar_total=False
):
    """Abre uma página da vitrine, espera os cartões renderizarem e extrai os dados."""
    separador = "&" if "?" in url_aba else "?"
    url_pagina = (
        url_aba if num_pagina == 1 else f"{url_aba}{separador}page={num_pagina}"
    )

    try:
        await aba_browser.goto(
            url_pagina, wait_until="domcontentloaded", timeout=30000
        )

        # Espera inteligente: aguarda até que os cartões de produto apareçam na tela (até 10s)
        try:
            await aba_browser.wait_for_selector(
                '.product-box, [data-testid="product-card"]', timeout=10000
            )
        except Exception:
            return num_pagina, [], 0

        # Rola até ao fim para carregar todas as imagens (Lazy Load)
        await aba_browser.evaluate(
            "window.scrollTo(0, document.body.scrollHeight)"
        )
        await aba_browser.wait_for_timeout(700)

        resultado = await aba_browser.evaluate(
            """(detectarTotal) => {
            const lista = [];
            const cartoes = document.querySelectorAll('.product-box, [data-testid="product-card"]');
            cartoes.forEach(cartao => {
                const marcaEl = cartao.querySelector('.product-box-brand, [data-testid="product-brand"]');
                let marca = marcaEl ? marcaEl.innerText.trim() : '';
                if (/^\\d+(\\.\\d+)?$/.test(marca)) marca = '';

                const tituloEl = cartao.querySelector('.product-box-title');
                const precoEl = cartao.querySelector('.product-box-price-to');
                const linkEl = cartao.querySelector('a[href]');
                const imgEl = cartao.querySelector('img');

                let titulo = tituloEl ? tituloEl.innerText.trim() : '';
                const titleAttr = linkEl ? (linkEl.getAttribute('title') || '').trim() : '';
                const altAttr = imgEl ? (imgEl.getAttribute('alt') || '').trim() : '';

                if (titleAttr.length > titulo.length) titulo = titleAttr;
                if ((!titulo || titulo.endsWith('...')) && altAttr.length > titulo.length) {
                    titulo = altAttr;
                }

                let urlImg = '';
                if (imgEl) {
                    urlImg = imgEl.getAttribute('data-src') || imgEl.getAttribute('data-original') || imgEl.getAttribute('src') || '';
                    if (urlImg.startsWith('//')) urlImg = 'https:' + urlImg;
                }

                let link = linkEl ? linkEl.getAttribute('href') : '';
                if (link && !link.startsWith('http')) link = 'https://www.dafiti.com.br' + link;
                link = link.split('?')[0];

                if (titulo && link) {
                    lista.push({
                        Marca: marca || 'Não informada',
                        Produto: titulo,
                        Preco_Atual: precoEl ? precoEl.innerText.trim() : 'Indisponível',
                        URL_Imagem: urlImg,
                        Link: link
                    });
                }
            });

            // Descobre o número máximo da barra de paginação
            let maxPag = 0;
            if (detectarTotal) {
                const linksPag = document.querySelectorAll('a[href*="page="], ul.pagination li, [data-testid*="pagination"] a');
                linksPag.forEach(el => {
                    const txt = (el.innerText || '').trim();
                    if (/^\\d+$/.test(txt)) {
                        const n = parseInt(txt, 10);
                        if (n > maxPag) maxPag = n;
                    }
                    const href = el.getAttribute('href') || '';
                    const match = href.match(/page=(\\d+)/);
                    if (match) {
                        const n = parseInt(match[1], 10);
                        if (n > maxPag) maxPag = n;
                    }
                });
            }

            return { lista, maxPag };
        }""",
            detectar_total,
        )

        return num_pagina, resultado["lista"], resultado["maxPag"]
    except Exception:
        return num_pagina, [], 0


async def inspecionar_pagina_produto(aba_browser, item):
    """Entra no link individual do produto para confirmar título oficial, loja ('Vendido por') e preço."""
    try:
        await aba_browser.goto(
            item["Link"], wait_until="domcontentloaded", timeout=20000
        )
        await aba_browser.wait_for_timeout(750)

        dados_internos = await aba_browser.evaluate("""() => {
            const h1 = document.querySelector('h1');
            const tituloOficial = h1 ? h1.innerText.trim() : '';
            const precoEl = document.querySelector('.catalog-detail-price-value, [data-testid="price-value"], .price-box-to');
            const precoOficial = precoEl ? precoEl.innerText.trim() : '';
            return {
                tituloOficial,
                precoOficial,
                textoPagina: document.body.innerText
            };
        }""")

        if dados_internos["tituloOficial"]:
            item["Produto"] = dados_internos["tituloOficial"]
            item["Titulo_Limpo"] = " ".join(
                dados_internos["tituloOficial"].lower().split()
            )

        if dados_internos["precoOficial"]:
            item["Preco_Atual"] = dados_internos["precoOficial"]

        texto_pagina = dados_internos["textoPagina"]
        match_seller = re.search(
            r"(Vendido\s+(?:e\s+entregue\s+)?por\s+[^\n\r]+)",
            texto_pagina,
            re.IGNORECASE,
        )
        if match_seller:
            frase = match_seller.group(1).strip()
            item["Info_Entrega_Completa"] = frase
            match_loja = re.search(
                r"Vendido(?:\s+e\s+entregue)?\s+por\s+(.+?)(?:\s+e\s+entregue|\s*$)",
                frase,
                re.IGNORECASE,
            )
            item["Vendedor"] = (
                match_loja.group(1).strip() if match_loja else frase
            )
        else:
            item["Vendedor"] = (
                "Produto Esgotado"
                if "esgotado" in texto_pagina.lower()
                else "Não identificado"
            )
            item["Info_Entrega_Completa"] = item["Vendedor"]

    except Exception:
        item["Vendedor"] = "Erro ao aceder"
        item["Info_Entrega_Completa"] = "Erro ao aceder"


# =====================================================================
# 4. FLUXO PRINCIPAL (CRONÓMETRO -> COLETA -> ANÁLISE -> DIAGNÓSTICO)
# =====================================================================
async def executar_tudo():
    # Regista o momento exato em que o programa iniciou
    inicio_execucao = datetime.now()
    str_inicio = inicio_execucao.strftime("%d/%m/%Y %H:%M:%S")

    produtos_por_link = {}
    colunas_base = [
        "Marca",
        "Produto",
        "Titulo_Limpo",
        "Preco_Atual",
        "Onde_Apareceu_Texto",
        "URL_Imagem",
        "Link",
    ]

    print("=" * 65)
    print(f"INÍCIO DA EXECUÇÃO: {str_inicio}")
    print("=" * 65)
    print(
        f"Iniciando varredura completa em todas as {len(ABAS_DO_SITE)} abas ({PAGINAS_SIMULTANEAS} páginas simultâneas)..."
    )
    print(
        "Dica: A qualquer momento podes premir Ctrl+C uma vez para parar a leitura e gerar o Excel com o que já foi recolhido!\n"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )

        abas_navegador = []
        for _ in range(PAGINAS_SIMULTANEAS):
            aba = await context.new_page()
            await aba.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type
                in ["stylesheet", "font", "media", "image"]
                else route.continue_(),
            )
            abas_navegador.append(aba)

        # -------------------------------------------------------------
        # ETAPA A: VARREDURA DE TODAS AS ABAS COM DETEÇÃO DE PÁGINAS
        # -------------------------------------------------------------
        try:
            for nome_aba, url_aba in ABAS_DO_SITE:
                print(f"\n=== Explorando Aba: {nome_aba} ({url_aba}) ===")

                _, itens_p1, total_paginas_aba = await ler_pagina_vitrine(
                    abas_navegador[0], nome_aba, url_aba, 1, detectar_total=True
                )

                if not itens_p1:
                    await asyncio.sleep(3)
                    _, itens_p1, total_paginas_aba = await ler_pagina_vitrine(
                        abas_navegador[0],
                        nome_aba,
                        url_aba,
                        1,
                        detectar_total=True,
                    )

                if not itens_p1:
                    print(
                        f"  [{nome_aba}] Nenhum produto encontrado nesta URL. Pulando para a próxima aba."
                    )
                    continue

                info_total = (
                    f"{total_paginas_aba} páginas detetadas"
                    if total_paginas_aba > 0
                    else "total dinâmico"
                )
                print(f"  [{nome_aba}] Catálogo ativo ({info_total}).")

                novos_p1 = 0
                links_lote_anterior = set()
                for item in itens_p1:
                    link_limpo = item["Link"]
                    links_lote_anterior.add(link_limpo)
                    localizacao = f"{nome_aba} (Pág 1)"
                    if link_limpo in produtos_por_link:
                        if (
                            localizacao
                            not in produtos_por_link[link_limpo][
                                "Onde_Apareceu"
                            ]
                        ):
                            produtos_por_link[link_limpo][
                                "Onde_Apareceu"
                            ].append(localizacao)
                    else:
                        nome_pelo_link = extrair_nome_do_link(link_limpo)
                        titulo_visivel_limpo = " ".join(
                            item["Produto"].lower().split()
                        )
                        item["Titulo_Limpo"] = (
                            nome_pelo_link
                            if (
                                titulo_visivel_limpo.endswith("...")
                                or len(nome_pelo_link)
                                > len(titulo_visivel_limpo)
                            )
                            else titulo_visivel_limpo
                        )
                        item["Onde_Apareceu"] = [localizacao]
                        item["Foto_ID"] = ""
                        item["Vendedor"] = ""
                        item["Info_Entrega_Completa"] = ""
                        produtos_por_link[link_limpo] = item
                        novos_p1 += 1

                label_tot = (
                    f"/{total_paginas_aba}" if total_paginas_aba > 0 else ""
                )
                print(
                    f"  [{nome_aba} | Pág 001{label_tot}] +{novos_p1} SKUs únicos | Total global: {len(produtos_por_link)}"
                )

                inicio_lote = 2
                tentativas_vazias = 0

                while True:
                    if (
                        total_paginas_aba > 0
                        and inicio_lote > total_paginas_aba
                    ):
                        print(
                            f"  [{nome_aba}] Todas as {total_paginas_aba} páginas foram lidas!"
                        )
                        break

                    fim_lote = inicio_lote + PAGINAS_SIMULTANEAS
                    if total_paginas_aba > 0:
                        fim_lote = min(fim_lote, total_paginas_aba + 1)

                    paginas_lote = list(range(inicio_lote, fim_lote))
                    if not paginas_lote:
                        break

                    tarefas = [
                        ler_pagina_vitrine(
                            abas_navegador[idx],
                            nome_aba,
                            url_aba,
                            num_pag,
                            detectar_total=False,
                        )
                        for idx, num_pag in enumerate(paginas_lote)
                    ]
                    resultados_lote = await asyncio.gather(*tarefas)

                    links_lote_atual = set()
                    novos_no_lote = 0
                    lote_vazio = True

                    for num_pag, itens, _ in resultados_lote:
                        if itens:
                            lote_vazio = False
                        localizacao = f"{nome_aba} (Pág {num_pag})"
                        for item in itens:
                            link_limpo = item["Link"]
                            links_lote_atual.add(link_limpo)
                            if link_limpo in produtos_por_link:
                                if (
                                    localizacao
                                    not in produtos_por_link[link_limpo][
                                        "Onde_Apareceu"
                                    ]
                                ):
                                    produtos_por_link[link_limpo][
                                        "Onde_Apareceu"
                                    ].append(localizacao)
                            else:
                                nome_pelo_link = extrair_nome_do_link(
                                    link_limpo
                                )
                                titulo_visivel_limpo = " ".join(
                                    item["Produto"].lower().split()
                                )
                                item["Titulo_Limpo"] = (
                                    nome_pelo_link
                                    if (
                                        titulo_visivel_limpo.endswith("...")
                                        or len(nome_pelo_link)
                                        > len(titulo_visivel_limpo)
                                    )
                                    else titulo_visivel_limpo
                                )
                                item["Onde_Apareceu"] = [localizacao]
                                item["Foto_ID"] = ""
                                item["Vendedor"] = ""
                                item["Info_Entrega_Completa"] = ""
                                produtos_por_link[link_limpo] = item
                                novos_no_lote += 1

                    if lote_vazio:
                        tentativas_vazias += 1
                        if tentativas_vazias <= 2:
                            print(
                                f"  [{nome_aba}] Lote {paginas_lote[0]}-{paginas_lote[-1]} demorou a responder. A tentar novamente ({tentativas_vazias}/2)..."
                            )
                            await asyncio.sleep(4)
                            continue
                        else:
                            print(
                                f"  [{nome_aba}] Fim real da aba atingido na página {inicio_lote}."
                            )
                            break

                    tentativas_vazias = 0

                    if links_lote_atual.issubset(links_lote_anterior):
                        print(
                            f"  [{nome_aba}] Paginação concluída na página {inicio_lote}."
                        )
                        break

                    links_lote_anterior = links_lote_atual
                    print(
                        f"  [{nome_aba} | Págs {paginas_lote[0]:03d}-{paginas_lote[-1]:03d}{label_tot}] +{novos_no_lote} SKUs únicos | Total global: {len(produtos_por_link)}"
                    )

                    # Checkpoint automático a cada 40 páginas
                    if (inicio_lote - 2) % 40 == 0 and inicio_lote > 2:
                        lista_temp = list(produtos_por_link.values())
                        for p_temp in lista_temp:
                            p_temp["Onde_Apareceu_Texto"] = " | ".join(
                                p_temp["Onde_Apareceu"]
                            )
                        arq_bkp = salvar_csv_seguro(
                            ARQUIVO_BASE, lista_temp, colunas_base
                        )
                        print(
                            f"    -> [Checkpoint] Base salva em '{arq_bkp}' ({len(lista_temp)} SKUs únicos)."
                        )

                    inicio_lote = fim_lote
                    await asyncio.sleep(0.5)

                lista_temp = list(produtos_por_link.values())
                for p_temp in lista_temp:
                    p_temp["Onde_Apareceu_Texto"] = " | ".join(
                        p_temp["Onde_Apareceu"]
                    )
                salvar_csv_seguro(ARQUIVO_BASE, lista_temp, colunas_base)

        except KeyboardInterrupt:
            print(
                "\n\n[Interrupção Manual] Coleta interrompida pelo utilizador. A analisar tudo o que já foi recolhido..."
            )

        # -------------------------------------------------------------
        # ETAPA B: CALCULAR HASH MD5 DAS IMAGENS E SALVAR BASE COMPLETA
        # -------------------------------------------------------------
        lista_unicos = list(produtos_por_link.values())
        print(
            f"\nColeta finalizada! Total de SKUs únicos recolhidos: {len(lista_unicos)}"
        )

        if not lista_unicos:
            await browser.close()
            fim_execucao = datetime.now()
            print(
                f"\nInício: {str_inicio} | Fim: {fim_execucao.strftime('%d/%m/%Y %H:%M:%S')} | Duração: {formatar_duracao(fim_execucao - inicio_execucao)}"
            )
            return

        print("A calcular a impressão digital visual (MD5) das imagens...")

        cache_hashes = {}
        headers_img = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0"
        }

        def calcular_hash_produto(produto):
            url_img = produto["URL_Imagem"]
            if not url_img or not url_img.startswith("http"):
                produto["Foto_ID"] = "SEM_IMAGEM"
                return produto
            if url_img in cache_hashes:
                produto["Foto_ID"] = cache_hashes[url_img]
                return produto
            try:
                resp = requests.get(url_img, headers=headers_img, timeout=10)
                if resp.status_code == 200:
                    hash_md5 = hashlib.md5(resp.content).hexdigest()
                    cache_hashes[url_img] = hash_md5
                    produto["Foto_ID"] = hash_md5
                else:
                    produto["Foto_ID"] = "ERRO_IMAGEM"
            except Exception:
                produto["Foto_ID"] = "ERRO_IMAGEM"
            return produto

        with ThreadPoolExecutor(max_workers=24) as executor:
            lista_unicos = list(executor.map(calcular_hash_produto, lista_unicos))

        for p in lista_unicos:
            p["Onde_Apareceu_Texto"] = " | ".join(p["Onde_Apareceu"])

        colunas_base_com_foto = [
            "Marca",
            "Produto",
            "Titulo_Limpo",
            "Preco_Atual",
            "Foto_ID",
            "Onde_Apareceu_Texto",
            "URL_Imagem",
            "Link",
        ]
        arq_base_salvo = salvar_csv_seguro(
            ARQUIVO_BASE, lista_unicos, colunas_base_com_foto
        )
        print(
            f"Base completa ({len(lista_unicos)} SKUs) guardada em: '{arq_base_salvo}'"
        )

        # -------------------------------------------------------------
        # ETAPA C: REGRA DUPLA DE DUPLICIDADE (TÍTULO IGUAL OU FOTO MD5 IGUAL)
        # -------------------------------------------------------------
        contagem_titulos = Counter(p["Titulo_Limpo"] for p in lista_unicos)
        contagem_fotos = Counter(
            p["Foto_ID"]
            for p in lista_unicos
            if p["Foto_ID"] not in ("SEM_IMAGEM", "ERRO_IMAGEM")
        )

        duplicados_candidatos = []
        for p in lista_unicos:
            tem_titulo_igual = contagem_titulos[p["Titulo_Limpo"]] > 1
            tem_foto_igual = (
                p["Foto_ID"] not in ("SEM_IMAGEM", "ERRO_IMAGEM")
                and contagem_fotos[p["Foto_ID"]] > 1
            )

            if tem_titulo_igual or tem_foto_igual:
                if tem_foto_igual:
                    p["Grupo_ID"] = f"FOTO_{p['Foto_ID'][:10]}"
                else:
                    p["Grupo_ID"] = f"TITULO_{p['Titulo_Limpo'][:35]}"
                duplicados_candidatos.append(p)

        print(
            f"\nAnúncios duplicados encontrados (Título igual OU Foto igual): {len(duplicados_candidatos)}"
        )

        # -------------------------------------------------------------
        # ETAPA D: INSPECIONAR PÁGINA INTERNA DE CADA DUPLICADO
        # -------------------------------------------------------------
        if duplicados_candidatos:
            print(
                "A visitar a página interna de cada duplicado para confirmar título, loja ('Vendido por') e preço..."
            )
            for i in range(0, len(duplicados_candidatos), PAGINAS_SIMULTANEAS):
                lote_dups = duplicados_candidatos[i : i + PAGINAS_SIMULTANEAS]
                tarefas_loja = [
                    inspecionar_pagina_produto(abas_navegador[idx], item)
                    for idx, item in enumerate(lote_dups)
                ]
                await asyncio.gather(*tarefas_loja)
                print(
                    f"  -> Inspecionados {min(i + PAGINAS_SIMULTANEAS, len(duplicados_candidatos))}/{len(duplicados_candidatos)} anúncios..."
                )

        await browser.close()

    # =================================================================
    # 5. DIAGNÓSTICO FINAL, CAMPO 'Obs', CRONÓMETRO E EXPORTAÇÃO
    # =================================================================
    fim_execucao = datetime.now()
    str_fim = fim_execucao.strftime("%d/%m/%Y %H:%M:%S")
    duracao_hhmmss = formatar_duracao(fim_execucao - inicio_execucao)

    if duplicados_candidatos:
        grupos = {}
        for item in duplicados_candidatos:
            grupos.setdefault(item["Grupo_ID"], []).append(item)

        resumo_motivos = Counter()
        lista_final_exportar = []

        for grupo_id, itens_grupo in grupos.items():
            if len(itens_grupo) < 2:
                continue

            vendedores = {i["Vendedor"].lower().strip() for i in itens_grupo}
            precos = {
                re.sub(r"\s+", "", i["Preco_Atual"]) for i in itens_grupo
            }
            titulos = {i["Titulo_Limpo"] for i in itens_grupo}
            fotos = {i["Foto_ID"] for i in itens_grupo}

            detalhes = []
            if len(vendedores) > 1:
                detalhes.append("Lojas Diferentes")
            if len(precos) > 1:
                detalhes.append("Valores Diferentes")
            if len(titulos) > 1:
                detalhes.append("Títulos Diferentes")
            if len(fotos) > 1:
                detalhes.append("Arquivos de Foto Diferentes (Mesmo Título)")

            if not detalhes:
                motivo = (
                    "Sem Diferença Aparente (Duplicidade Pura: Mesma Foto, Título, Loja e Preço)"
                )
            elif len(vendedores) == 1 and len(precos) == 1 and len(titulos) == 1:
                motivo = (
                    "Sem Diferença Aparente (Duplicidade Pura - Foto re-comprimida no servidor)"
                )
            else:
                motivo = " + ".join(detalhes)

            resumo_motivos[motivo] += len(itens_grupo)

            for i in itens_grupo:
                i["Qtd_SKUs_Duplicados"] = len(itens_grupo)
                i["Motivo_Duplicidade"] = motivo
                i["Obs"] = (
                    f"{motivo} | {i['Info_Entrega_Completa']} | Onde apareceu: {i['Onde_Apareceu_Texto']}"
                )
                i["Data_Hora_Inicio"] = str_inicio
                i["Data_Hora_Fim"] = str_fim
                i["Duracao"] = duracao_hhmmss
                lista_final_exportar.append(i)

        lista_final_exportar.sort(
            key=lambda x: (
                -x["Qtd_SKUs_Duplicados"],
                x["Grupo_ID"],
                x["Vendedor"],
            )
        )

        colunas_dup = [
            "Qtd_SKUs_Duplicados",
            "Motivo_Duplicidade",
            "Obs",
            "Vendedor",
            "Preco_Atual",
            "Marca",
            "Produto",
            "Info_Entrega_Completa",
            "Onde_Apareceu_Texto",
            "Grupo_ID",
            "Link",
            "URL_Imagem",
            "Data_Hora_Inicio",
            "Data_Hora_Fim",
            "Duracao",
        ]
        arq_dup_salvo = salvar_csv_seguro(
            ARQUIVO_DUPLICADOS, lista_final_exportar, colunas_dup
        )

        print("\n" + "=" * 65)
        print("RESUMO DOS MOTIVOS DE DUPLICIDADE ENCONTRADOS:")
        for mot, qtd in resumo_motivos.items():
            print(f" - {mot}: {qtd} anúncios")
        print("-" * 65)
        print(f"Data/Hora Início : {str_inicio}")
        print(f"Data/Hora Fim    : {str_fim}")
        print(f"Duração Total    : {duracao_hhmmss}")
        print("=" * 65)
        print(f"Sucesso! Ficheiro de duplicados guardado em: '{arq_dup_salvo}'")
    else:
        print("\n" + "=" * 65)
        print("Nenhuma duplicidade foi encontrada.")
        print(f"Data/Hora Início : {str_inicio}")
        print(f"Data/Hora Fim    : {str_fim}")
        print(f"Duração Total    : {duracao_hhmmss}")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(executar_tudo())