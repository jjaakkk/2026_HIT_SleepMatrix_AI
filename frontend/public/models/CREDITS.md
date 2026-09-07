# 3D 模型署名与许可

## Soldier.glb（当前使用）

- 模型：Soldier（军人角色，含面部/护目镜，Mixamo 骨骼 rig）
- 来源：three.js 官方示例模型仓库
  https://github.com/mrdoob/three.js/blob/dev/examples/models/gltf/Soldier.glb
- 骨骼：49 根 `mixamorig:*` 标准骨骼（与 Mixamo 生态兼容，可无缝替换其他 Mixamo 角色）
- 许可：随 three.js 示例发布，署名使用（原模型出自 Adobe Mixamo；
  Mixamo 资产允许在应用内免费使用，禁止作为素材单独转售/再分发）。
  本项目仅将模型嵌入应用演示，未做再分发，并在本文件保留来源署名。

## 床垫 / 气囊条带

床垫与气囊分区条带为程序化几何（three.js 生成），不包含第三方模型资产。

## 历史

- 曾使用 Cesium `RiggedFigure`（CC BY 4.0），因模型质量/比例不佳（无面部特征、
  肩宽过高导致侧卧观感差）已替换为 Soldier.glb。
