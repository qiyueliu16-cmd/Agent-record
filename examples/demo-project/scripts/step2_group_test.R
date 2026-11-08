# 示例脚本｜本仓库所有数据均为合成演示数据，不对应任何真实研究结果。
# 运行需要 R；工作台只登记路径，不执行代码。

df <- read.csv("results/summary.csv", stringsAsFactors = FALSE)
x <- subset(df, group == "A")$log2CPM
y <- subset(df, group == "B")$log2CPM
wilcox.test(x, y, conf.int = TRUE, exact = FALSE)
