# 示例脚本｜本仓库所有数据均为合成演示数据，不对应任何真实研究结果。
# 运行需要 R；工作台只登记路径，不执行代码。

df <- read.csv("results/summary.csv", stringsAsFactors = FALSE)
stopifnot(all(c("group", "log2CPM", "n_cells", "detect_rate") %in% names(df)))
aggregate(cbind(n_cells, log2CPM, detect_rate) ~ group, data = df, FUN = median)
