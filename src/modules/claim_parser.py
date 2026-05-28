import re


def parse_uSs(uSs: str) -> list[dict]:
    """
    マイクロサービスの文字列表現を解析して、構造化されたデータに変換します。
    
    Args:
        uSs: マイクロサービスの文字列表現（例: "Microservice(name='service1', build=Build(...), confidence=0.8)"）
        
    Returns:
        マイクロサービスの情報を含む辞書のリスト。各辞書には名前、ビルド情報、信頼度が含まれます。
        入力が "set()" の場合は None を返します。
    """
    # 空のセットの場合はNoneを返す
    if uSs == "set()":
        return None

    # マイクロサービスの情報を抽出するための正規表現パターン
    pattern = r"Microservice\(name='(.*?)', build=Build\((.*?)\), confidence=(.*?)\)"
    matches = re.findall(pattern, uSs)

    result = []

    # 各マッチしたマイクロサービス情報を処理
    for match in matches:
        build = {}
        # ビルド情報を解析
        build["context"] = eval(match[1].split(",")[0].split("=")[1])
        build["rel_dockerfile"] = eval(match[1].split(",")[1].split("=")[1])
        build["remote"] = eval(match[1].split(",")[2].split("=")[1])
        build["absolute"] = eval(match[1].split(",")[3].split("=")[1])

        # 構造化されたデータを作成
        result.append({
            "name": match[0],
            "build": build,
            "confidence": match[2]
        })

    return result


def parse_containers(containers: str) -> list[dict]:
    """
    コンテナの文字列表現を解析して、構造化されたデータに変換します。
    
    Args:
        containers: コンテナの文字列表現（例: "Container(image='image1', build=Build(...), container_name='container1')"）
        
    Returns:
        コンテナの情報を含む辞書のリスト。各辞書にはイメージ名、ビルド情報、コンテナ名が含まれます。
        入力が "set()" の場合は None を返します。
    """
    # 空のセットの場合はNoneを返す
    if containers == "set()":
        return None

    # コンテナの情報を抽出するための正規表現パターン
    pattern = r"Container\(image=(.*?), build=(.*?), container_name='(.*?)'\)"
    matches = re.findall(pattern, containers)

    result = []

    # 各マッチしたコンテナ情報を処理
    for match in matches:
        build = {}
        # ビルド情報がある場合のみ解析
        if match[1] != "None":
            build_text = match[1].replace("Build(", "").replace(")", "")
            build["context"] = eval(build_text.split(",")[0].split("=")[1])
            build["rel_dockerfile"] = eval(build_text.split(",")[1].split("=")[1])
            build["remote"] = eval(build_text.split(",")[2].split("=")[1])
            build["absolute"] = eval(build_text.split(",")[3].split("=")[1])

        # 構造化されたデータを作成
        result.append({
            "image": eval(match[0]),
            "build": build,
            "container_name": match[2]
        })

    return result