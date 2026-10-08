# 96点实测代码来源

上游仓库：https://github.com/zhangqian-1/jingneng-power-forecast-observations-20261008

固定提交：4a38c670cfcf1271244a5127018a618ecdcdc301。

- `result_contract.py` 来自上游 `app/result_contract.py`，内容不变。
- `contract.py`、`storage.py` 来自上游 `observations_service/`，仅把 `from app.result_contract import` 改为相对导入 `from .result_contract import`。
- 不改测点映射、归零、缺测、站级统计、偏差公式、归档及修正实测规则。
- 联合层只向这套存储提供已发布的北京时间当天曲线，不同步滚动 latest 曲线。预测实际生成时间与联合层首次保存时间共同约束偏差，事后补算不生成过去时刻的事前偏差。
- `api.py`、启动器等上游HTTP进程不在本目录运行；联合接口直接调用无模型依赖的实测模块。预测模型仍运行于独立的原镜像环境。
