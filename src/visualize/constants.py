from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# ---------------------------------------------------------------------------
# メトリクス定義
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricDef:
    """クローンメトリクス 1 件の定義.

    Attributes:
        key: 対応するデータクラスのフィールド名 (compute_clone_metrics.py).
        label_en: 英語ラベル.
        label_ja: 日本語ラベル.
        description: 概要説明（日本語）.
        granularity: メトリクスの粒度.
        filter_type: フィルタ UI の種別.
            ``"range"`` → 数値範囲スライダー,
            ``"enum"``  → 選択式ドロップダウン.
        unit: 表示単位（省略可）.
    """

    key: str
    label_en: str
    label_ja: str
    description: str
    granularity: Literal["service", "clone_set", "file"]
    filter_type: Literal["range", "enum"]
    unit: str = ""


class CloneMetricRegistry:
    """クローンメトリクス定義のレジストリ.

    各クラス変数が MetricDef 1 件に対応する.
    ``by_granularity(granularity)`` でフィルタ UI 用のリストを取得できる.

    粒度別の対応:
        - service   → ServiceMetrics  (compute_clone_metrics.py)
        - clone_set → CloneSetMetrics (compute_clone_metrics.py)
        - file      → FileMetrics     (compute_clone_metrics.py)
    """

    # ------------------------------------------------------------------
    # サービス（MS）粒度
    # ------------------------------------------------------------------

    SERVICE_CLONE_SET_COUNT = MetricDef(
        key="clone_set_count",
        label_en="Number of clone sets",
        label_ja="クローンセット数",
        description="当該 MS にフラグメントが 1 件以上存在するクローンセット数（intra / inter 問わず）．",
        granularity="service",
        filter_type="range",
    )

    SERVICE_INTER_CLONE_SET_COUNT = MetricDef(
        key="inter_clone_set_count",
        label_en="Number of inter-service clone sets",
        label_ja="サービス間クローンセット数",
        description="跨り MS 数 ≥ 2 のクローンセット数（サービス間クローンのみ）．",
        granularity="service",
        filter_type="range",
    )

    SERVICE_TOTAL_CLONE_LOC = MetricDef(
        key="total_clone_line_count",
        label_en="Total clone LOC",
        label_ja="合計クローン行数",
        description="当該 MS に属するクローン行数の合計（ファイルごとに区間マージし重複を除去）．",
        granularity="service",
        filter_type="range",
        unit="lines",
    )

    SERVICE_AVG_CLONE_LOC = MetricDef(
        key="clone_avg_line_count",
        label_en="Average clone LOC",
        label_ja="平均クローン行数",
        description="当該 MS に属するクローンフラグメント 1 件あたりの平均 LOC．",
        granularity="service",
        filter_type="range",
        unit="lines",
    )

    SERVICE_FILE_COUNT = MetricDef(
        key="clone_file_count",
        label_en="Number of files in clone sets",
        label_ja="関連ファイル数",
        description="当該 MS に含まれるクローンフラグメントが存在するファイル数．",
        granularity="service",
        filter_type="range",
    )

    SERVICE_ROC = MetricDef(
        key="roc",
        label_en="Ratio of clone lines (ROC)",
        label_ja="ROC（クローン行割合）",
        description="当該 MS の総 LOC に対するクローン LOC の割合．"
        " ROC = clone LOC / total LOC of MS",
        granularity="service",
        filter_type="range",
        unit="%",
    )

    SERVICE_COMOD_COUNT = MetricDef(
        key="comod_count",
        label_en="Simultaneous modification count",
        label_ja="同時修正回数",
        description="当該 MS が関与する同時修正コミット数（複数クローンセットにまたがるコミットも 1 回とカウント）．",
        granularity="service",
        filter_type="range",
    )

    SERVICE_COMOD_OTHER_SERVICE_COUNT = MetricDef(
        key="comod_other_service_count",
        label_en="Number of clone-sharing microservices",
        label_ja="共有クローン MS 数",
        description="当該 MS とクローンセットを共有している他 MS の数．",
        granularity="service",
        filter_type="range",
    )

    # ------------------------------------------------------------------
    # クローンセット（CS）粒度
    # ------------------------------------------------------------------

    CS_SERVICE_COUNT = MetricDef(
        key="service_count",
        label_en="Number of involved microservices",
        label_ja="跨り MS 数",
        description="クローンセットが何個の MS に分布しているか．"
        " サービス間判定: 跨り MS 数 ≥ 2",
        granularity="clone_set",
        filter_type="range",
    )

    CS_CROSS_SERVICE_LOC = MetricDef(
        key="cross_service_line_count",
        label_en="Inter-service clone LOC",
        label_ja="サービス間クローン行数",
        description="クローンセット内のサービス間フラグメントの LOC 合計．",
        granularity="clone_set",
        filter_type="range",
        unit="lines",
    )

    CS_CROSS_FRAGMENT_RATIO = MetricDef(
        key="cross_service_fragment_ratio",
        label_en="Inter-service clone ratio (fragment LOC)",
        label_ja="サービス間クローン割合（フラグメント行数）",
        description="サービス間クローンに 1 度でも関与したフラグメント集合 F_inter の行数が"
        " 全フラグメント行数に占める割合．"
        " Σ LOC(f∈F_inter) / Σ LOC(f∈F)",
        granularity="clone_set",
        filter_type="range",
        unit="%",
    )

    CS_CROSS_SCALE = MetricDef(
        key="cross_service_scale",
        label_en="Inter-service clone scale",
        label_ja="サービス間クローンスケール",
        description="サービス間フラグメント数 × サービス間 LOC の積（規模指標）．",
        granularity="clone_set",
        filter_type="range",
    )

    CS_COMOD_COUNT = MetricDef(
        key="comod_count",
        label_en="Simultaneous modification count",
        label_ja="同時修正回数",
        description="クローンセットに関係する複数箇所が同一コミット内で"
        " 同時修正された回数．対象コミット集合は検出設定に依存．",
        granularity="clone_set",
        filter_type="range",
    )

    CS_COMOD_FRAGMENT_COUNT = MetricDef(
        key="comod_fragment_count",
        label_en="Number of co-modified fragments",
        label_ja="同時修正フラグメント数",
        description="同時修正コミットに関与したフラグメントの件数．",
        granularity="clone_set",
        filter_type="range",
    )

    CS_COMOD_FRAGMENT_RATIO = MetricDef(
        key="comod_fragment_ratio",
        label_en="Co-modified fragment ratio",
        label_ja="同時修正フラグメント割合",
        description="全フラグメント数に対する同時修正フラグメント数の割合．",
        granularity="clone_set",
        filter_type="range",
        unit="%",
    )

    # ------------------------------------------------------------------
    # ファイル粒度
    # ------------------------------------------------------------------

    FILE_SHARING_SERVICE_COUNT = MetricDef(
        key="sharing_service_count",
        label_en="Number of shared microservices",
        label_ja="共有 MS 数",
        description="当該ファイルのクローンセットを共有している MS 数（自分以外）．",
        granularity="file",
        filter_type="range",
    )

    FILE_TOTAL_SERVICE_COUNT = MetricDef(
        key="total_service_count",
        label_en="Total number of microservices",
        label_ja="総 MS 数",
        description="プロジェクト全体の MS 数（共有 MS 割合の分母）．",
        granularity="file",
        filter_type="range",
    )

    FILE_CROSS_CS_COUNT = MetricDef(
        key="cross_service_clone_set_count",
        label_en="Number of shared clone sets",
        label_ja="共有クローンセット数",
        description="当該ファイルが他 MS のファイルと共有しているクローンセット数．",
        granularity="file",
        filter_type="range",
    )

    FILE_CROSS_CS_RATIO = MetricDef(
        key="cross_service_clone_set_ratio",
        label_en="Ratio of shared clone sets",
        label_ja="共有クローンセット割合",
        description="当該ファイルが含まれるクローンセットのうち，"
        " 他 MS と共有しているものの割合．",
        granularity="file",
        filter_type="range",
        unit="%",
    )

    FILE_SHARING_SERVICE_RATIO = MetricDef(
        key="sharing_service_ratio",
        label_en="Shared microservices / total microservices",
        label_ja="共有 MS 割合",
        description="共有 MS 数を総 MS 数で正規化した値．",
        granularity="file",
        filter_type="range",
        unit="%",
    )

    FILE_CROSS_LOC = MetricDef(
        key="cross_service_line_count",
        label_en="Inter-service clone LOC",
        label_ja="サービス間クローン行数",
        description="当該ファイルのうち，他 MS と共有しているクローン部分の行数合計．",
        granularity="file",
        filter_type="range",
        unit="lines",
    )

    FILE_CROSS_COMOD_COUNT = MetricDef(
        key="cross_service_comod_count",
        label_en="Inter-service simultaneous modification count",
        label_ja="サービス間同時修正回数",
        description="他 MS と共有している（inter）クローンセットに限定した同時修正回数．"
        " 他 MS との結合リスクを表す．",
        granularity="file",
        filter_type="range",
    )

    FILE_COMOD_SHARED_SERVICE_COUNT = MetricDef(
        key="comod_shared_service_count",
        label_en="Number of simultaneously modified microservices",
        label_ja="同時修正関連 MS 数",
        description="コードクローンに関する同時修正を共有した MS 数．",
        granularity="file",
        filter_type="range",
    )

    # ------------------------------------------------------------------
    # ヘルパー
    # ------------------------------------------------------------------

    @classmethod
    def all(cls) -> list[MetricDef]:
        """全粒度の MetricDef を定義順に返す."""
        return [
            v for v in cls.__dict__.values() if isinstance(v, MetricDef)
        ]

    @classmethod
    def by_granularity(
        cls, granularity: Literal["service", "clone_set", "file"]
    ) -> list[MetricDef]:
        """指定した粒度の MetricDef リストを返す."""
        return [m for m in cls.all() if m.granularity == granularity]

    @classmethod
    def get_filter_options(
        cls, granularity: Literal["service", "clone_set", "file"]
    ) -> list[dict]:
        """Dash Dropdown / Checklist 用のオプションリストを生成する.

        Returns:
            ``[{"label": "<ja> (<en>)", "value": "<key>"}, ...]``
        """
        return [
            {"label": f"{m.label_ja}  /  {m.label_en}", "value": m.key}
            for m in cls.by_granularity(granularity)
        ]

    @classmethod
    def get_by_key(cls, key: str) -> MetricDef | None:
        """フィールド名キーから MetricDef を検索する."""
        for m in cls.all():
            if m.key == key:
                return m
        return None


class DetectionMethod:
    """検出手法に関する定数定義"""
    
    # 内部識別子
    NO_IMPORT = 'no-import'
    TKS = 'tks'
    CCFSW = 'ccfsw'  # Legacy (raw output with imports)

    # UI表示用ラベル
    LABELS = {
        NO_IMPORT: 'Normal',  # "Normal" means No-Import in UI
        TKS: 'TKS',
        CCFSW: 'Legacy (Raw)'
    }

    # ファイルプレフィックスとのマッピング
    # prefix (without underscore) -> method
    PREFIX_MAP = {
        'import': NO_IMPORT,
        'tks': TKS,
        '': CCFSW
    }

    @classmethod
    def get_options(cls):
        """UIコンポーネント用のオプションリストを生成"""
        # UIには Normal (No-Import) と TKS のみを表示するのが基本方針
        return [
            {'label': cls.LABELS[cls.NO_IMPORT], 'value': cls.NO_IMPORT},
            {'label': cls.LABELS[cls.TKS], 'value': cls.TKS}
        ]

    @classmethod
    def from_prefix(cls, prefix):
        """ファイルプレフィックスからメソッドを特定"""
        if prefix is None:
            prefix = ''
        # 末尾のアンダースコアを除去して小文字化
        clean_prefix = prefix.lower().rstrip('_')
        return cls.PREFIX_MAP.get(clean_prefix, cls.CCFSW)
