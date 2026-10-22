"""轻量表格类型：项目所需的 pandas.DataFrame 最小子集。

背景
----
``pandas`` 安装体积约 69MB、导入约 0.49s，而本项目对它的实际用法
只有"带列序的字典列表 + CSV 读写 + 少量布尔掩码筛选"。核心链路
（数据读取 / 训练报告 / 指标提取 / 批量 / 导出）为此背上整个 pandas
并不划算。

本模块提供 :class:`Table` 及配套助手，覆盖项目用到的全部 DataFrame 语义：

- 构造：``Table(rows)``（list[dict]）、``Table(matrix, index=, columns=)``
- 访问：``.columns`` / ``.index`` / ``.empty`` / ``.__len__``
- 取列：``table["scope"]`` → :class:`Column`（支持逐元素 ``==`` / ``&``）
- 筛选：``table[mask]`` / ``table[mask1 & mask2]`` → 新 :class:`Table`
- 取行：``.iloc[0]`` → dict（支持 ``[]`` 与 ``.get``）、``.iterrows()``
- 结构：``.insert(pos, name, values)`` / ``.pop(name)`` / ``.T``
- 输出：``.to_csv(path, index=, encoding=)`` / ``.to_dict("records")``
- 读写：:func:`read_csv` / :func:`isna` / :func:`notna` / :func:`to_numeric`

不在范围内（研究脚本请继续用 pandas）：``.loc`` 标签索引、``groupby``、
多级索引、缺失值填充、``dropna(axis=1)`` 之外的 NaN 语义等。

与 pandas 的有意语义差异（均为"宽松化"，项目内无依赖严格报错的调用方）：

- 构造时 ``index`` 长度与行数不匹配：pandas raise；Table 静默回退为
  ``range(n)`` 索引（保留原索引名）
- ``insert`` 重名列：pandas raise；Table 覆盖同名列值
- 布尔上下文：pandas raise；Table 返回"是否非空"
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np

__all__ = [
    "Column",
    "Index",
    "Mask",
    "Table",
    "isna",
    "notna",
    "read_csv",
    "to_numeric",
]


# --------------------------------------------------------------------------
# 缺失值判定
# --------------------------------------------------------------------------
def isna(value: Any) -> bool:
    """判定缺失值：None / NaN / NaT / 空字符串之外的 pandas.isna 语义子集。

    与 ``pandas.isna`` 的差异：pandas 不把空字符串视为缺失；此处保持一致。
    """
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, np.floating):
        return bool(np.isnan(value))
    if isinstance(value, complex) and math.isnan(value.real):
        return True
    return False


def notna(value: Any) -> bool:
    return not isna(value)


def to_numeric(value: Any, default: float | None = None) -> Any:
    """标量转数值；失败时返回 ``default``（缺省 nan）。

    ``pandas.to_numeric(..., errors="coerce")`` 的单值等价物。
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan") if default is None else default


# --------------------------------------------------------------------------
# 列 / 掩码
# --------------------------------------------------------------------------
class Mask(list):
    """逐元素布尔掩码，支持 ``&`` / ``|`` / ``~``（与 pandas 一致）。"""

    def __and__(self, other: Iterable[bool]) -> Mask:
        return Mask(bool(a) and bool(b) for a, b in zip(self, other))

    def __or__(self, other: Iterable[bool]) -> Mask:
        return Mask(bool(a) or bool(b) for a, b in zip(self, other))

    def __invert__(self) -> Mask:
        return Mask(not bool(a) for a in self)


class Column:
    """一列数据：支持逐元素比较产生 :class:`Mask`。"""

    __slots__ = ("_values",)

    def __init__(self, values: Iterable[Any]) -> None:
        self._values = list(values)

    # --- 容器协议 ---
    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __getitem__(self, item: Any) -> Any:
        return self._values[item]

    def __contains__(self, value: Any) -> bool:
        return value in self._values

    def __repr__(self) -> str:
        return f"Column({self._values!r})"

    # --- 逐元素比较（返回 Mask，与 pandas 语义一致）---
    def _elementwise(self, other: Any, op: Any) -> Mask:
        if isinstance(other, Column):
            other = other._values
        if isinstance(other, (list, tuple, Mask)):
            return Mask(op(a, b) for a, b in zip(self._values, other))
        return Mask(op(a, other) for a in self._values)

    def __eq__(self, other: object) -> Any:  # type: ignore[override]
        return self._elementwise(other, lambda a, b: a == b)

    def __ne__(self, other: object) -> Any:  # type: ignore[override]
        return self._elementwise(other, lambda a, b: a != b)

    def __lt__(self, other: Any) -> Mask:
        return self._elementwise(other, lambda a, b: a < b)

    def __le__(self, other: Any) -> Mask:
        return self._elementwise(other, lambda a, b: a <= b)

    def __gt__(self, other: Any) -> Mask:
        return self._elementwise(other, lambda a, b: a > b)

    def __ge__(self, other: Any) -> Mask:
        return self._elementwise(other, lambda a, b: a >= b)

    def __and__(self, other: Any) -> Mask:
        return self._elementwise(other, lambda a, b: bool(a) and bool(b))

    def __or__(self, other: Any) -> Mask:
        return self._elementwise(other, lambda a, b: bool(a) or bool(b))

    def __invert__(self) -> Mask:
        return Mask(not bool(a) for a in self._values)

    def __hash__(self) -> None:  # type: ignore[override]
        return None  # type: ignore[return-value]

    # --- 便捷 ---
    def tolist(self) -> list[Any]:
        return list(self._values)

    def to_numpy(self, dtype: Any = None) -> np.ndarray:
        """返回列值的 ndarray（与 ``pandas.Series.to_numpy`` 等价）。"""
        array = np.asarray(self._values)
        return array.astype(dtype) if dtype is not None else array

    @property
    def values(self) -> list[Any]:
        return self._values


class Index:
    """行索引：支持 ``.name``（与 pandas 一致，导出 CSV 时作为首列表头）。"""

    __slots__ = ("_labels", "name")

    def __init__(self, labels: Iterable[Any], name: str | None = None) -> None:
        self._labels = list(labels)
        self.name = name

    def __len__(self) -> int:
        return len(self._labels)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._labels)

    def __getitem__(self, item: Any) -> Any:
        return self._labels[item]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Index):
            return self._labels == other._labels
        if isinstance(other, list):
            return self._labels == other
        return NotImplemented

    def __repr__(self) -> str:
        return f"Index({self._labels!r}, name={self.name!r})"

    def tolist(self) -> list[Any]:
        return list(self._labels)

    def to_numpy(self, dtype: Any = None) -> np.ndarray:
        """返回 Index 标签的 ndarray 视图（与 ``pandas.Index.to_numpy`` 等价）。"""
        array = np.asarray(self._labels)
        return array.astype(dtype) if dtype is not None else array


class _ILoc:
    """``table.iloc[i]`` —— 位置索引，返回 dict 行（支持 ``[]`` / ``.get``）。"""

    __slots__ = ("_table",)

    def __init__(self, table: Table) -> None:
        self._table = table

    def __getitem__(self, item: Any) -> Any:
        rows = self._table._rows
        if isinstance(item, tuple):
            row_idx, col_idx = item
            return rows[row_idx][col_idx]
        if isinstance(item, slice):
            return Table(rows[item], columns=self._table._columns)
        return dict(rows[item])


# --------------------------------------------------------------------------
# 表
# --------------------------------------------------------------------------
class Table:
    """带列序的轻量二维表（list[dict] 之上的薄封装）。"""

    def __init__(
        self,
        data: Any = None,
        columns: Sequence[str] | None = None,
        index: Iterable[Any] | None = None,
    ) -> None:
        self.index: Index = Index(index if index is not None else [])
        self._rows: list[dict[str, Any]] = []
        self._columns: list[str] = []

        if data is None:
            if columns is not None:
                self._columns = [str(c) for c in columns]
            return

        if isinstance(data, Table):
            self._rows = [dict(r) for r in data._rows]
            self._columns = list(data._columns)
            if index is None:
                self.index = Index(data.index.tolist(), data.index.name)
            return

        if isinstance(data, np.ndarray):
            self._init_from_matrix(data, columns, index)
            return

        if isinstance(data, dict):
            # dict[str, sequence]：列名 -> 列值
            self._columns = [str(k) for k in data]
            length = 0
            for values in data.values():
                length = max(length, len(list(values)))
            self._rows = [
                {key: list(data[key])[i] for key in data} for i in range(length)
            ]
            if columns is not None:
                self._columns = [str(c) for c in columns]
            return

        rows = list(data)
        if rows and isinstance(rows[0], dict):
            keys: list[Any] = []
            for row in rows:
                for key in row:
                    if key not in keys:
                        keys.append(key)
            if columns is not None:
                # pandas 语义：显式 columns 时只保留这些列（缺失填 NaN）
                keys = list(columns)
            self._columns = keys
            self._rows = [
                {key: row.get(key, float("nan")) for key in keys} for row in rows
            ]
        else:
            # list[list] / list[tuple] 等序列
            if columns is not None:
                self._columns = [str(c) for c in columns]
            else:
                width = len(rows[0]) if rows else 0
                self._columns = [str(i) for i in range(width)]
            self._rows = [
                {col: row[i] for i, col in enumerate(self._columns)} for row in rows
            ]

        if index is None:
            self.index = Index(range(len(self._rows)))
        if len(self.index) != len(self._rows):
            self.index = Index(range(len(self._rows)), self.index.name)

    def _init_from_matrix(
        self,
        matrix: np.ndarray,
        columns: Sequence[Any] | None,
        index: Iterable[Any] | None,
    ) -> None:
        array = np.asarray(matrix)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        n_rows, n_cols = array.shape
        # 保留原始标签类型（float 标签不应被强制转 str —— 与 pandas 行为一致）
        self._columns = list(columns) if columns is not None else [
            str(i) for i in range(n_cols)
        ]
        if index is not None:
            self.index = Index(index)
        else:
            self.index = Index(range(n_rows))
        if len(self.index) != n_rows:
            self.index = Index(range(n_rows), self.index.name)
        self._rows = [
            {self._columns[j]: array[i, j] for j in range(n_cols)}
            for i in range(n_rows)
        ]

    # --- 结构访问 ---
    @property
    def columns(self) -> Index:
        return Index(self._columns)

    @columns.setter
    def columns(self, value: Sequence[str]) -> None:
        new = [str(v) for v in value]
        if len(new) != len(self._columns):
            raise ValueError(
                f"列数不匹配: 新 {len(new)} vs 现有 {len(self._columns)}"
            )
        rename = dict(zip(self._columns, new))
        self._rows = [{rename[k]: v for k, v in row.items()} for row in self._rows]
        self._columns = new

    @property
    def empty(self) -> bool:
        return not self._rows

    @property
    def iloc(self) -> _ILoc:
        return _ILoc(self)

    @property
    def shape(self) -> tuple[int, int]:
        return len(self._rows), len(self._columns)

    def __len__(self) -> int:
        return len(self._rows)

    def __bool__(self) -> bool:
        # 与 pandas 的有意差异：DataFrame 在布尔上下文会 raise
        # （"truth value is ambiguous"）；Table 选择返回"是否非空"，
        # 便于 ``if table:`` 判空写法。
        return not self.empty

    def __repr__(self) -> str:
        return f"Table(rows={len(self._rows)}, columns={self._columns})"

    # --- 取列 / 筛选 ---
    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if key not in self._columns:
                raise KeyError(key)
            return Column(row.get(key) for row in self._rows)
        if isinstance(key, (Mask, Column)):
            return self._filter(list(key))
        if isinstance(key, (list, tuple)) and key and all(
            isinstance(k, (bool, np.bool_)) for k in key
        ):
            return self._filter(list(key))
        if isinstance(key, (list, tuple)):
            names = [str(k) for k in key]
            missing = [n for n in names if n not in self._columns]
            if missing:
                raise KeyError(f"列不存在: {missing}")
            return Table([{n: row.get(n) for n in names} for row in self._rows])
        raise KeyError(f"不支持的索引: {key!r}")

    def _filter(self, mask: Sequence[Any]) -> Table:
        rows = [row for row, keep in zip(self._rows, mask) if bool(keep)]
        indices = [idx for idx, keep in zip(self.index.tolist(), mask) if bool(keep)]
        result = Table(rows, columns=self._columns)
        result.index = Index(indices, self.index.name)
        return result

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self._columns:
            self._columns.append(key)
        if isinstance(value, (Column, Mask)):
            value = list(value)
        if isinstance(value, (list, tuple)):
            for row, item in zip(self._rows, value):
                row[key] = item
            if key not in self._columns:
                self._columns.append(key)
            return
        for row in self._rows:
            row[key] = value

    def get(self, key: str, default: Any = None) -> Column | Any:
        if key in self._columns:
            return self[key]
        return default

    # --- 结构操作 ---
    def insert(self, loc: int, column: str, value: Any) -> None:
        """在 ``loc`` 位置插入一列（与 ``DataFrame.insert`` 一致）。"""
        name = str(column)
        if isinstance(value, (Column, Mask)):
            values = list(value)
        elif isinstance(value, (list, tuple)):
            values = list(value)
        else:
            values = [value] * len(self._rows)
        for i, row in enumerate(self._rows):
            row[name] = values[i] if i < len(values) else float("nan")
        self._columns.insert(loc, name)

    def pop(self, column: str) -> Column:
        """移除并返回一列（与 ``DataFrame.pop`` 一致）。"""
        name = str(column)
        if name not in self._columns:
            raise KeyError(name)
        values = Column(row.pop(name, float("nan")) for row in self._rows)
        self._columns.remove(name)
        return values

    @property
    def T(self) -> Table:
        """转置：原行标签成为列名，原列名成为行标签（与 ``DataFrame.T`` 一致）。

        例如 ``Table([{"a": 1, "b": 2}])`` 的转置为
        ``[{0: 1}, {0: 2}]``（索引标签 0 成为唯一列名）。
        """
        labels = self.index.tolist()
        if not self._rows:
            result = Table()
            result._columns = list(labels)
            return result
        rows = [
            {label: row.get(col) for label, row in zip(labels, self._rows)}
            for col in self._columns
        ]
        result = Table(rows)
        result._columns = list(labels)
        result.index = Index(self._columns)
        return result

    def iterrows(self) -> Iterator[tuple[Any, dict[str, Any]]]:
        for label, row in zip(self.index.tolist(), self._rows):
            yield label, dict(row)

    def itertuples(self) -> Iterator[tuple[Any, ...]]:
        for row in self._rows:
            yield tuple(row.get(c) for c in self._columns)

    def dropna(self, axis: int = 0, how: str = "any") -> Table:
        """仅支持 ``axis=1, how="all"``（数据读取时丢弃全空列）。"""
        if axis != 1:
            raise NotImplementedError("Table.dropna 仅实现 axis=1")
        if how != "all":
            raise NotImplementedError("Table.dropna 仅实现 how='all'")
        keep = [
            col
            for col in self._columns
            if not all(isna(row.get(col)) for row in self._rows)
        ]
        return Table([{c: row.get(c) for c in keep} for row in self._rows],
                     columns=keep)

    def to_numpy(self, dtype: Any = None) -> np.ndarray:
        array = np.array(
            [[row.get(c) for c in self._columns] for row in self._rows]
        )
        if dtype is not None:
            return array.astype(dtype)
        return array

    def to_dict(self, orient: str = "dict") -> Any:
        if orient == "records":
            return [dict(row) for row in self._rows]
        if orient == "list":
            return {c: [row.get(c) for row in self._rows] for c in self._columns}
        if orient == "dict":
            return {c: [row.get(c) for row in self._rows] for c in self._columns}
        raise ValueError(f"不支持的 orient: {orient}")

    def to_string(self, index: bool = True) -> str:
        """对齐的纯文本表格（``DataFrame.to_string`` 的最小等价物）。

        数值单元格右对齐、其余左对齐（与 pandas 一致）；缺失值显示为空；
        ``index=False`` 时不输出索引列。供研究脚本 CLI 打印使用。
        """
        def _is_numeric(text: str) -> bool:
            if not text:
                return False
            try:
                float(text)
            except ValueError:
                return False
            return True

        header: list[str] = ([self.index.name or ""] if index else []) + [
            str(c) for c in self._columns
        ]
        body = [
            ([str(label)] if index else [])
            + ["" if isna(row.get(c)) else str(row.get(c)) for c in self._columns]
            for label, row in self.iterrows()
        ]
        widths = [
            max([len(header[i])] + [len(r[i]) for r in body])
            for i in range(len(header))
        ]
        lines = [" ".join(h.rjust(widths[i]) for i, h in enumerate(header)).rstrip()]
        for r in body:
            cells = [
                r[i].rjust(widths[i]) if _is_numeric(r[i]) else r[i].ljust(widths[i])
                for i in range(len(header))
            ]
            lines.append(" ".join(cells).rstrip())
        return "\n".join(lines)

    def to_csv(
        self,
        path: Any,
        index: bool = True,
        encoding: str | None = "utf-8",
        sep: str = ",",
    ) -> None:
        """写出 CSV：``path`` 接受路径或文件型对象（与 ``DataFrame.to_csv`` 一致）。

        - 路径 / PathLike：以 ``encoding`` 打开文件
        - 文件型对象（``BytesIO``/已打开文件）：使用对象自身并忽略 ``encoding``
          （调用方负责已写对象的编码模式）。
        """
        header: list[Any] = []
        if index:
            header.append(self.index.name if self.index.name else "")
        header.extend(self._columns)

        def _write_to(handle: Any) -> None:
            # 字节流（如 BytesIO / BufferedRandom）需包成 TextIOWrapper
            # 才能用 csv.writer；若底层对象无 "b" 模式则按文本流处理
            mode = getattr(handle, "mode", None)
            is_bytes = (
                "b" in mode
                if isinstance(mode, str)
                else isinstance(handle, (io.BytesIO, io.BufferedIOBase))
            )
            if is_bytes:
                text_handle = io.TextIOWrapper(
                    handle, encoding=encoding or "utf-8",
                    newline="", write_through=True,
                )
                try:
                    writer = csv.writer(text_handle, delimiter=sep)
                    _write_rows(writer, header)
                finally:
                    text_handle.detach()
                return
            writer = csv.writer(handle, delimiter=sep)
            _write_rows(writer, header)

        def _write_rows(writer: csv.writer, head: list[Any]) -> None:
            writer.writerow(head)
            for label, row in self.iterrows():
                line: list[Any] = []
                if index:
                    line.append(label)
                line.extend(row.get(c) for c in self._columns)
                writer.writerow(line)

        if hasattr(path, "write"):
            _write_to(path)
            return

        target = Path(path)
        with target.open("w", newline="", encoding=encoding or "utf-8") as handle:
            _write_to(handle)


# --------------------------------------------------------------------------
# CSV 读取
# --------------------------------------------------------------------------
def read_csv(
    path: str | Path,
    sep: str = ",",
    encoding: str = "utf-8-sig",
    header: int | None = "infer",
    skiprows: int | None = None,
    dtype: Any = None,
) -> Table:
    """项目所需的 :func:`pandas.read_csv` 子集。

    支持：自定义分隔符、编码、无表头（``header=None``）、跳过前 N 行
    （``skiprows``）与强制字符串（``dtype=str``）。

    编码默认 ``utf-8-sig``：自动剥离 BOM（pandas 默认行为一致），
    接收 utf-8 / utf-8-sig 文件无需额外开关。无 BOM 输入不受影响。
    不支持注释行、多字符引号、na_values 等进阶参数。

    空字段语义与 pandas 一致：空白字段（含行尾多余分隔符产生的尾列）
    一律转为 NaN——即使 ``dtype=str``（pandas 在 ``dtype=str`` 下同样
    将空字段解析为 NaN）。这保证 ``dropna(axis=1, how="all")`` 能正确
    丢弃全空尾列，避免下游 ``to_numpy(dtype=float)`` 在 "" 上崩溃。
    """
    path = Path(path)
    with path.open("r", newline="", encoding=encoding) as handle:
        raw_rows = list(csv.reader(handle, delimiter=sep))

    if skiprows:
        raw_rows = raw_rows[skiprows:]

    if header is None:
        width = max((len(r) for r in raw_rows), default=0)
        columns = [str(i) for i in range(width)]
        data_rows = raw_rows
    else:
        if not raw_rows:
            return Table()
        head = raw_rows[0]
        columns = [str(c) for c in head]
        data_rows = raw_rows[1:]

    nan = float("nan")
    rows: list[dict[str, Any]] = []
    for raw in data_rows:
        # pandas 语义：空字段 -> NaN；dtype=str 仅保证非空字段保持字符串
        values = [nan if v == "" else v for v in raw]
        values += [nan] * (len(columns) - len(values))
        rows.append({columns[i]: values[i] for i in range(len(columns))})
    return Table(rows, columns=columns)
