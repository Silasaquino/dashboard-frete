# ==========================================
    # CARREGAMENTO CONSOLIDADO MULTI-SHEETS DA BASE (5 SHEETS PELO NOME DA ABA)
    # ==========================================
    SHEETS_BASE_IDS = [
        "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU",  # Parte 1 (Principal)
        "10zd0gTWei38fpjBZ4xNuIe0gdI8FGbscX3bc6uYgewE",  # Parte 2
        "1FBS9BSal8DBtyVSOhGKBcNIa8EmktSunsuCCC9AuM34",  # Parte 3
        "17f48qNZ1MVvgOwI467OypCrgR-iQl3TqZ7sosLp3s7Y",  # Parte 4
        "1AyYe3M3kHCnlZYjD-GSR9oHr_6rGqsL8KMBUnnrvcx4"   # Parte 5
    ]

    SHEET_ID_RESUMO = "1tYkxqGCSan5C7wAjtqKeKpOE2OeGCgrzSynMaXVBaKU"

    @st.cache_data(ttl=3600)
    def carregar_dados_reversa_consolidados():
        """Lê a aba 'BASE' de cada um dos 5 links pelo nome da folha e junta em um DataFrame."""
        lista_dfs = []
        for sheet_id in SHEETS_BASE_IDS:
            # Busca diretamente a aba com o nome 'BASE', eliminando a dependência do 'gid'
            url_csv = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BASE"
            try:
                df_temp = pd.read_csv(url_csv)
                if not df_temp.empty and len(df_temp.columns) > 1:
                    lista_dfs.append(df_temp)
            except Exception as e:
                print(f"⚠️ Erro ao carregar Sheet ID {sheet_id}: {e}")

        if lista_dfs:
            return pd.concat(lista_dfs, ignore_index=True)
        else:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def carregar_dados_resumo():
        """Lê a aba RESUMO REVERSA do link único principal."""
        url_csv_resumo = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_RESUMO}/gviz/tq?tqx=out:csv&sheet=RESUMO%20REVERSA"
        try:
            df_resumo = pd.read_csv(url_csv_resumo)
            return df_resumo
        except Exception as e:
            st.error(f"Erro ao carregar dados da folha 'RESUMO REVERSA': {e}")
            return pd.DataFrame()