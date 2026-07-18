# 旧材料只读哈希基线元数据

## 基线摘要

- 基线生成时间：`2026-07-18T19:44:29+1000`（AEST，UTC+10:00）
- 旧材料位置：相对于项目根目录的 `../论文与实习`
- 普通文件数：75
- 子目录数：21（不含旧材料根目录本身）
- 普通文件总字节数：74,097,025
- 哈希算法：SHA-256
- 清单文件：`docs/audit/legacy_hashes.before.sha256`
- 清单聚合哈希：`f534b2543beb31e8f0253001b96494b0086b4b085a340d8d4ae4d33e10c91e8e`

## 可重现算法

1. 从项目根目录进入旧材料相对路径 `../论文与实习`。
2. 使用 `find . -type f -print0` 枚举全部普通文件，以 NUL 分隔路径。
3. 使用 `LC_ALL=C sort -z` 按路径字节稳定排序。
4. 对每个文件执行 `shasum -a 256`，每行写为 `SHA-256`、两个 ASCII 空格、去掉开头 `./` 的相对路径及换行。
5. 聚合哈希定义为正式清单文件完整字节序列（包括每行换行及最终换行）的 SHA-256；重现命令为：

   ```bash
   shasum -a 256 docs/audit/legacy_hashes.before.sha256
   ```

生成正式清单时实际执行：

```bash
/bin/bash -c 'set -euo pipefail
(
  cd ../论文与实习
  find . -type f -print0 \
    | LC_ALL=C sort -z \
    | while IFS= read -r -d "" legacy_path; do
        legacy_hash=$(shasum -a 256 "$legacy_path")
        printf "%s  %s\n" "${legacy_hash%% *}" "${legacy_path#./}"
      done
) > docs/audit/legacy_hashes.before.sha256'
```

只读统计命令：

```bash
find ../论文与实习 -type f -print0 | tr -cd '\000' | wc -c
find ../论文与实习 -mindepth 1 -type d -print0 | tr -cd '\000' | wc -c
find ../论文与实习 -type f -exec stat -f '%z' -- {} + \
  | awk '{ total += $1 } END { printf "%.0f\n", total }'
```

## 项目 Git 现场

- 当前分支：`main`
- 当前 HEAD：`23f08f5a61b8317d6837c0157057904637a58447`
- origin URL：`git@github.com:xulong-jia/PathPlanningLab.git`
- upstream：`origin/main`

## 旧材料保护声明

- 旧材料执行代码：否
- 旧材料修改：否
- 在旧目录创建缓存、日志或临时文件：否
- Python、Notebook、宏或其他旧材料可执行文件运行：否
