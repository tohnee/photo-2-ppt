---
license: apache-2.0
library_name: PaddleOCR
language:
- en
- zh
pipeline_tag: image-to-text
tags:
- OCR
- PaddlePaddle
- PaddleOCR
- formula_recognition
---

# PP-FormulaNet_plus-L

## Introduction

PP-FormulaNet_plus is an enhanced version of the formula recognition model developed by the PaddleOCR Team, building upon the original PP-FormulaNet. Compared to the original version, PP-FormulaNet_plus utilizes a more diverse formula dataset during training, including sources such as Chinese dissertations, professional books, textbooks, exam papers, and mathematics journals. This expansion significantly improves the model’s recognition capabilities. The PP-FormulaNet_plus includes multiple versions: L, M, and S, where PP-FormulaNet_plus-L have added support for Chinese formulas and increased the maximum number of predicted tokens for formulas from 1,024 to 2,560, greatly enhancing the recognition performance for complex formulas. The key accuracy metrics are as follow:


| Model           | Backbone     | En-BLEU↑ |Zh-BLEU(%)↑  | GPU Inference Time (ms)| 
|:----------------:|:---------:|:-----------------:|:--------------:|:--------------:|
| UniMERNet | Donut Swin |    85.91  |   43.50       | 2266.96 | 
| PP-FormulaNet-S | PPHGNetV2_B4 |   87.00   |   45.71   | 202.25 |
| PP-FormulaNet-L | Vary_VIT_B |    90.36   |    45.78        | 1976.52  |
| PP-FormulaNet_plus-S | PPHGNetV2_B4  |     88.71   |     53.32        |     	191.69  |
| PP-FormulaNet_plus-M | PPHGNetV2_B6 |    91.45   |     89.76        |     	1301.56    |
|  <b>PP-FormulaNet_plus-L</b> |   <b>Vary_VIT_B</b> |  <b>92.22</b>   |   <b>90.64</b>     |   <b>1745.25 </b>    |
| LaTeX-OCR | Hybrid ViT |  74.55   |       39.96        | 	1244.61   |

Note: En-BLEU and Zh-BLEU (%) represent the BLEU scores for English formulas and Chinese formulas, respectively. The evaluation dataset for English formulas includes simple and complex formulas from UniMERNet, as well as simple, intermediate, and complex formulas from PaddleX’s internally developed dataset. The evaluation dataset for Chinese formulas comes from PaddleX’s internally developed Chinese formula dataset.

## Quick Start

### Installation

1. PaddlePaddle

Please refer to the following commands to install PaddlePaddle using pip:

```bash
# for CUDA11.8
python -m pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

# for CUDA12.6
python -m pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

# for CPU
python -m pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

For details about PaddlePaddle installation, please refer to the [PaddlePaddle official website](https://www.paddlepaddle.org.cn/en/install/quick).

2. PaddleOCR

Install the latest version of the PaddleOCR inference package from PyPI:

```bash
python -m pip install paddleocr
```

### Model Usage

You can quickly experience the functionality with a single command:

```bash
paddleocr formula_recognition \
    --model_name PP-FormulaNet_plus-L  \
    -i https://cdn-uploads.huggingface.co/production/uploads/68493f0616e67d38f02f138a/4kkIUGxXMGozIg6U1BIxZ.png
```

You can also integrate the model inference of the formula recognition module into your project. Before running the following code, please download the [sample image](https://cdn-uploads.huggingface.co/production/uploads/68493f0616e67d38f02f138a/4kkIUGxXMGozIg6U1BIxZ.png) to your local machine.

```python
from paddleocr import FormulaRecognition
model = FormulaRecognition(model_name="PP-FormulaNet_plus-L")
output = model.predict(input="4kkIUGxXMGozIg6U1BIxZ.png", batch_size=1)
for res in output:
    res.print()
    res.save_to_img(save_path="./output/")
    res.save_to_json(save_path="./output/res.json")
```

After running, the obtained result is as follows:

```json
{'res': {'input_path': '4kkIUGxXMGozIg6U1BIxZ.png', 'page_index': None, 'rec_formula': '\\zeta_{0}(\\nu)=-\\frac{\\nu\\varrho^{-2\\nu}}{\\pi}\\int_{\\mu}^{\\infty}d\\omega\\int_{C_{+}}d z\\frac{2z^{2}}{(z^{2}+\\omega^{2})^{\\nu+1}}\\breve{\\Psi}(\\omega;z)e^{i\\epsilon z}\\quad,'}}
```
<b>Note: If you need to visualize the formula recognition module, you must install the LaTeX rendering environment by running the following command. Currently, visualization is only supported on Ubuntu. Other environments are not supported for now. For complex formulas, the LaTeX result may contain advanced representations that may not render successfully in Markdown or similar environments:</b>
```bash
sudo apt-get update
sudo apt-get install texlive texlive-latex-base texlive-xetex latex-cjk-all texlive-latex-extra -y
```

The visualized image is as follows:

![image/jpeg](https://cdn-uploads.huggingface.co/production/uploads/68493f0616e67d38f02f138a/Vj5bQYm32zZAUs959zCUw.png)

For details about usage command and descriptions of parameters, please refer to the [Document](https://paddlepaddle.github.io/PaddleOCR/latest/en/version3.x/module_usage/formula_recognition.html#iii-quick-start).

### Pipeline Usage

The ability of a single model is limited. But the pipeline consists of several models can provide more capacity to resolve difficult problems in real-world scenarios.

#### Formula Recognition Pipeline

The formula recognition pipeline is designed to solve formula recognition tasks by extracting formula information from images and outputting it in LaTeX source code format. And there are 4 modules in the pipeline: 
* Document Image Orientation Classification Module (Optional)
* Text Image Unwarping Module (Optional)
* Layout Detection Module (Optional)
* Formula Recognition Module

Run a single command to quickly experience the Formula Recognition Pipeline. Before running the code below, please download the [example image](https://cdn-uploads.huggingface.co/production/uploads/68493f0616e67d38f02f138a/4HrLNUf2yKGI8CwN9axpt.png) locally:

```bash
paddleocr formula_recognition_pipeline -i https://cdn-uploads.huggingface.co/production/uploads/68493f0616e67d38f02f138a/4HrLNUf2yKGI8CwN9axpt.png \
    --formula_recognition_model_name PP-FormulaNet_plus-L  \
    --save_path ./output \
    --device gpu:0 
```

Results are printed to the terminal:

```json
{'res': {'input_path': '/root/.paddlex/predict_input/4HrLNUf2yKGI8CwN9axpt.png', 'page_index': None, 'model_settings': {'use_doc_preprocessor': True, 'use_layout_detection': True}, 'doc_preprocessor_res': {'input_path': None, 'page_index': None, 'model_settings': {'use_doc_orientation_classify': True, 'use_doc_unwarping': True}, 'angle': 0}, 'layout_det_res': {'input_path': None, 'page_index': None, 'boxes': [{'cls_id': 2, 'label': 'text', 'score': 0.9855162501335144, 'coordinate': [90.5582, 1086.7775, 658.8992, 1553.267]}, {'cls_id': 2, 'label': 'text', 'score': 0.9814791679382324, 'coordinate': [93.042145, 127.992386, 664.8606, 396.60297]}, {'cls_id': 2, 'label': 'text', 'score': 0.9767233729362488, 'coordinate': [698.44617, 591.048, 1293.3668, 748.28625]}, {'cls_id': 2, 'label': 'text', 'score': 0.9712724089622498, 'coordinate': [701.4879, 286.62286, 1299.0151, 391.8841]}, {'cls_id': 2, 'label': 'text', 'score': 0.9708836078643799, 'coordinate': [697.0071, 751.9401, 1290.2227, 883.6447]}, {'cls_id': 2, 'label': 'text', 'score': 0.9688520431518555, 'coordinate': [704.01917, 79.636734, 1304.7367, 187.96138]}, {'cls_id': 2, 'label': 'text', 'score': 0.9683284163475037, 'coordinate': [93.07703, 799.36597, 660.6864, 902.0364]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9660061597824097, 'coordinate': [728.5604, 440.9317, 1224.097, 570.8568]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9615049958229065, 'coordinate': [723.025, 1333.5005, 1257.1569, 1468.0688]}, {'cls_id': 7, 'label': 'formula', 'score': 0.961004376411438, 'coordinate': [777.5282, 207.88376, 1222.9387, 267.32993]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9609803557395935, 'coordinate': [756.4403, 1211.3208, 1188.0408, 1268.2334]}, {'cls_id': 2, 'label': 'text', 'score': 0.959402322769165, 'coordinate': [697.5221, 957.6737, 1288.6223, 1033.5424]}, {'cls_id': 2, 'label': 'text', 'score': 0.9592350125312805, 'coordinate': [691.3296, 1511.7983, 1282.0968, 1642.5952]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9590734839439392, 'coordinate': [153.89197, 924.2169, 601.09546, 1036.9056]}, {'cls_id': 2, 'label': 'text', 'score': 0.9582054615020752, 'coordinate': [87.024506, 1557.2972, 655.9558, 1632.701]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9579665064811707, 'coordinate': [810.86975, 1057.1064, 1175.1078, 1117.6572]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9557791352272034, 'coordinate': [165.2392, 557.844, 598.2451, 614.3662]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9539064764976501, 'coordinate': [116.46484, 713.8796, 614.2107, 774.029]}, {'cls_id': 2, 'label': 'text', 'score': 0.9520670175552368, 'coordinate': [96.68561, 478.32416, 662.5837, 536.60223]}, {'cls_id': 2, 'label': 'text', 'score': 0.9442729949951172, 'coordinate': [96.14572, 639.16113, 661.80334, 692.4822]}, {'cls_id': 2, 'label': 'text', 'score': 0.940317690372467, 'coordinate': [695.9426, 1138.6841, 1286.7327, 1188.0151]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9249900579452515, 'coordinate': [852.94556, 908.64923, 1131.185, 933.8394]}, {'cls_id': 7, 'label': 'formula', 'score': 0.9248911142349243, 'coordinate': [195.27357, 424.8133, 567.68335, 451.1208]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.9173402786254883, 'coordinate': [1246.2461, 1079.063, 1286.333, 1104.3276]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.9168799519538879, 'coordinate': [1246.8928, 908.664, 1288.1958, 934.6163]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.915979266166687, 'coordinate': [1247.0377, 1229.1577, 1287.0939, 1254.9792]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.9086456894874573, 'coordinate': [1252.8517, 492.109, 1294.6124, 518.47156]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.9016352891921997, 'coordinate': [1242.1753, 1473.7004, 1283.019, 1498.6516]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.9000396728515625, 'coordinate': [1269.8044, 220.35562, 1299.8611, 247.01315]}, {'cls_id': 7, 'label': 'formula', 'score': 0.8966289758682251, 'coordinate': [95.999916, 235.48334, 295.44852, 265.59302]}, {'cls_id': 2, 'label': 'text', 'score': 0.8954761028289795, 'coordinate': [696.8688, 1286.2268, 1083.3927, 1310.8733]}, {'cls_id': 7, 'label': 'formula', 'score': 0.8951668739318848, 'coordinate': [166.62683, 129.18127, 511.6576, 156.2976]}, {'cls_id': 2, 'label': 'text', 'score': 0.8934891819953918, 'coordinate': [725.67053, 396.18787, 1263.0408, 422.78894]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.892305314540863, 'coordinate': [634.14246, 427.77844, 661.17773, 454.10535]}, {'cls_id': 2, 'label': 'text', 'score': 0.8891267776489258, 'coordinate': [94.483185, 1058.7578, 441.93515, 1082.4932]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.8877044320106506, 'coordinate': [630.4214, 939.2977, 657.7117, 965.36]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.8832477927207947, 'coordinate': [630.59216, 1000.9552, 657.4265, 1026.2094]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.8769293427467346, 'coordinate': [634.1151, 575.3828, 660.59314, 601.1638]}, {'cls_id': 7, 'label': 'formula', 'score': 0.8733161091804504, 'coordinate': [95.2839, 1320.377, 264.92313, 1345.8511]}, {'cls_id': 17, 'label': 'formula_number', 'score': 0.8703839182853699, 'coordinate': [633.8277, 730.3137, 659.84564, 755.55347]}, {'cls_id': 7, 'label': 'formula', 'score': 0.8392633199691772, 'coordinate': [365.18652, 268.2967, 515.7993, 296.06952]}, {'cls_id': 7, 'label': 'formula', 'score': 0.8316442370414734, 'coordinate': [1090.5394, 1599.1625, 1276.672, 1622.1669]}, {'cls_id': 7, 'label': 'formula', 'score': 0.817266583442688, 'coordinate': [246.17564, 161.22665, 314.3683, 186.41296]}, {'cls_id': 3, 'label': 'number', 'score': 0.8043113350868225, 'coordinate': [1297.4021, 7.143423, 1310.6084, 27.74441]}, {'cls_id': 7, 'label': 'formula', 'score': 0.797702968120575, 'coordinate': [538.4617, 478.0895, 661.8972, 508.51443]}, {'cls_id': 7, 'label': 'formula', 'score': 0.7646714448928833, 'coordinate': [916.5115, 1618.5238, 1009.6382, 1640.8141]}, {'cls_id': 7, 'label': 'formula', 'score': 0.7432729005813599, 'coordinate': [694.83765, 1612.2528, 861.0532, 1635.9652]}, {'cls_id': 7, 'label': 'formula', 'score': 0.7072135806083679, 'coordinate': [99.70873, 508.2096, 254.92291, 535.7488]}, {'cls_id': 7, 'label': 'formula', 'score': 0.6994448304176331, 'coordinate': [696.79846, 1561.4436, 899.79236, 1586.7415]}, {'cls_id': 7, 'label': 'formula', 'score': 0.6704866886138916, 'coordinate': [1117.0674, 1572.0345, 1191.5293, 1594.7426]}, {'cls_id': 7, 'label': 'formula', 'score': 0.6333382725715637, 'coordinate': [577.34186, 1274.4236, 602.5528, 1296.696]}, {'cls_id': 7, 'label': 'formula', 'score': 0.621163010597229, 'coordinate': [175.29213, 349.82397, 241.25047, 376.66553]}, {'cls_id': 7, 'label': 'formula', 'score': 0.6146791577339172, 'coordinate': [773.0735, 595.1659, 800.43823, 617.38635]}, {'cls_id': 7, 'label': 'formula', 'score': 0.6107904314994812, 'coordinate': [706.67114, 316.8644, 736.7178, 339.93387]}, {'cls_id': 7, 'label': 'formula', 'score': 0.5521712899208069, 'coordinate': [1263.9779, 314.65396, 1292.8451, 337.40207]}, {'cls_id': 7, 'label': 'formula', 'score': 0.5341379046440125, 'coordinate': [1219.2937, 316.60284, 1243.9319, 339.71375]}, {'cls_id': 7, 'label': 'formula', 'score': 0.520746111869812, 'coordinate': [254.65915, 323.65292, 326.58456, 349.53452]}, {'cls_id': 7, 'label': 'formula', 'score': 0.5011299848556519, 'coordinate': [255.84404, 1350.6619, 301.73444, 1375.5315]}]}, 'formula_res_list': [{'rec_formula': '\\begin{aligned}\\psi_{0}(M)-\\psi(M,z)=&\\frac{(1-\\epsilon_{r})}{\\epsilon_{r}}\\frac{\\lambda^{2}c^{2}}{t_{\\mathrm{E}}^{2}\\ln(10)}\\times\\\\&\\int_{0}^{z}d z^{\\prime}\\frac{d t}{d z^{\\prime}}\\left.\\frac{\\partial\\phi}{\\partial L}\\right|_{L=\\lambda M c^{2}/t_{\\mathrm{E}}},\\end{aligned}', 'formula_region_id': 1, 'dt_polys': ([728.5604, 440.9317, 1224.097, 570.8568],)}, {'rec_formula': '\\begin{aligned}{p(\\operatorname{l o g}_{10}}&{{}M|\\operatorname{l o g}_{10}\\sigma)=\\frac{1}{\\sqrt{2\\pi}\\epsilon_{0}}}\\\\ {}&{{}\\times\\operatorname{e x p}\\left[-\\frac{1}{2}\\left(\\frac{\\operatorname{l o g}_{10}M-a_{\\bullet}-b_{\\bullet}\\operatorname{l o g}_{10}\\sigma}{\\epsilon_{0}}\\right)^{2}\\right].}\\\\ \\end{aligned}', 'formula_region_id': 2, 'dt_polys': ([723.025, 1333.5005, 1257.1569, 1468.0688],)}, {'rec_formula': '\\phi(L)\\equiv\\frac{d n}{d\\log_{10}L}=\\frac{\\phi_{*}}{(L/L_{*})^{\\gamma_{1}}+(L/L_{*})^{\\gamma_{2}}}.', 'formula_region_id': 3, 'dt_polys': ([777.5282, 207.88376, 1222.9387, 267.32993],)}, {'rec_formula': '\\psi_{0}(M)=\\int d\\sigma\\frac{p(\\log_{10}M|\\log_{10}\\sigma)}{M\\log(10)}\\frac{d n}{d\\sigma}(\\sigma),', 'formula_region_id': 4, 'dt_polys': ([756.4403, 1211.3208, 1188.0408, 1268.2334],)}, {'rec_formula': '\\begin{align*}\\rho_{\\mathrm{BH}}&=\\int d M\\psi(M)M\\\\&=\\frac{1-\\epsilon_r}{\\epsilon_r c^2}\\int_{0}^{\\infty}d z\\frac{d t}{d z}\\int d\\log_{10}L\\phi(L,z)L,\\end{align*}', 'formula_region_id': 5, 'dt_polys': ([153.89197, 924.2169, 601.09546, 1036.9056],)}, {'rec_formula': '\\frac{d n}{d\\sigma}d\\sigma=\\psi_{*}\\left(\\frac{\\sigma}{\\sigma_{*}}\\right)^{\\alpha}\\frac{e^{-(\\sigma/\\sigma_{*})^{\\beta}}}{\\Gamma(\\alpha/\\beta)}\\beta\\frac{d\\sigma}{\\sigma}.', 'formula_region_id': 6, 'dt_polys': ([810.86975, 1057.1064, 1175.1078, 1117.6572],)}, {'rec_formula': '\\langle\\dot{M}(M,t)\\rangle\\psi(M,t)=\\frac{(1-\\epsilon_{r})}{\\epsilon_{r}c^{2}\\ln(10)}\\phi(L,t)\\frac{d L}{d M}.', 'formula_region_id': 7, 'dt_polys': ([165.2392, 557.844, 598.2451, 614.3662],)}, {'rec_formula': '\\frac{\\partial\\psi}{\\partial t}(M,t)+\\frac{(1-\\epsilon_{r})}{\\epsilon_{r}}\\frac{\\lambda^{2}c^{2}}{t_{\\mathrm{E}}^{2}\\ln(10)}\\left.\\frac{\\partial\\phi}{\\partial L}\\right|_{L=\\lambda M c^{2}/t_{\\mathrm{E}}}=0,', 'formula_region_id': 8, 'dt_polys': ([116.46484, 713.8796, 614.2107, 774.029],)}, {'rec_formula': '\\log_{10}M=a_{\\bullet}+b_{\\bullet}\\log_{10}X.', 'formula_region_id': 9, 'dt_polys': ([852.94556, 908.64923, 1131.185, 933.8394],)}, {'rec_formula': '\\phi(L,t)d\\log_{10}L=\\delta(M,t)\\psi(M,t)d M.', 'formula_region_id': 10, 'dt_polys': ([195.27357, 424.8133, 567.68335, 451.1208],)}, {'rec_formula': '\\dot{M}\\:=\\:(1-\\epsilon_{r})\\dot{M}_{\\mathrm{a c c}}^{-}', 'formula_region_id': 11, 'dt_polys': ([95.999916, 235.48334, 295.44852, 265.59302],)}, {'rec_formula': 't_{E}=\\sigma_{T}c/4\\pi G m_{p}=4.5\\times10^{8}\\mathrm{y r}', 'formula_region_id': 12, 'dt_polys': ([166.62683, 129.18127, 511.6576, 156.2976],)}, {'rec_formula': 'M_{*}\\bar{=L_{*}t_{E}/\\lambda c^{2}}', 'formula_region_id': 13, 'dt_polys': ([95.2839, 1320.377, 264.92313, 1345.8511],)}, {'rec_formula': '\\phi(L,t)d\\log_{10}L', 'formula_region_id': 14, 'dt_polys': ([365.18652, 268.2967, 515.7993, 296.06952],)}, {'rec_formula': 'a_{\\bullet}=8.32\\pm0.05', 'formula_region_id': 15, 'dt_polys': ([1090.5394, 1599.1625, 1276.672, 1622.1669],)}, {'rec_formula': '\\epsilon_{r}\\dot{M}_{\\mathrm{a c c}}', 'formula_region_id': 16, 'dt_polys': ([246.17564, 161.22665, 314.3683, 186.41296],)}, {'rec_formula': '\\langle\\dot{M}(M,t)\\rangle=', 'formula_region_id': 17, 'dt_polys': ([538.4617, 478.0895, 661.8972, 508.51443],)}, {'rec_formula': '\\epsilon_{0}=0.38', 'formula_region_id': 18, 'dt_polys': ([916.5115, 1618.5238, 1009.6382, 1640.8141],)}, {'rec_formula': 'b_{\\bullet}=5.64\\pm0.\\hat{3}2', 'formula_region_id': 19, 'dt_polys': ([694.83765, 1612.2528, 861.0532, 1635.9652],)}, {'rec_formula': '\\delta(M,t)\\dot{M}(M,t)', 'formula_region_id': 20, 'dt_polys': ([99.70873, 508.2096, 254.92291, 535.7488],)}, {'rec_formula': 'X\\:=\\:\\sigma/200\\mathrm{{k m}\\sigma\\mathrm{{s}^{-1}}}', 'formula_region_id': 21, 'dt_polys': ([696.79846, 1561.4436, 899.79236, 1586.7415],)}, {'rec_formula': 'M-\\sigma', 'formula_region_id': 22, 'dt_polys': ([1117.0674, 1572.0345, 1191.5293, 1594.7426],)}, {'rec_formula': 'L_{*}', 'formula_region_id': 23, 'dt_polys': ([577.34186, 1274.4236, 602.5528, 1296.696],)}, {'rec_formula': '\\phi(L,t)', 'formula_region_id': 24, 'dt_polys': ([175.29213, 349.82397, 241.25047, 376.66553],)}, {'rec_formula': '\\psi_{0}', 'formula_region_id': 25, 'dt_polys': ([773.0735, 595.1659, 800.43823, 617.38635],)}, {'rec_formula': " A''", 'formula_region_id': 26, 'dt_polys': ([706.67114, 316.8644, 736.7178, 339.93387],)}, {'rec_formula': 'L_{*}', 'formula_region_id': 27, 'dt_polys': ([1263.9779, 314.65396, 1292.8451, 337.40207],)}, {'rec_formula': '\\phi_{*}', 'formula_region_id': 28, 'dt_polys': ([1219.2937, 316.60284, 1243.9319, 339.71375],)}, {'rec_formula': '\\delta(M,t)', 'formula_region_id': 29, 'dt_polys': ([254.65915, 323.65292, 326.58456, 349.53452],)}, {'rec_formula': '\\phi(L)', 'formula_region_id': 30, 'dt_polys': ([255.84404, 1350.6619, 301.73444, 1375.5315],)}]}}
```

If save_path is specified, the visualization results will be saved under `save_path`. The visualization output is shown below:

![image/jpeg](https://cdn-uploads.huggingface.co/production/uploads/68493f0616e67d38f02f138a/tRGswcs4Bo2_jxSl_B-Wu.png)

The command-line method is for quick experience. For project integration, also only a few codes are needed as well:

```python
from paddleocr import FormulaRecognitionPipeline

pipeline = FormulaRecognitionPipeline(formula_recognition_model_name="PP-FormulaNet_plus-L")
output = pipeline.predict("./4HrLNUf2yKGI8CwN9axpt.png")
for res in output:
    res.print() ##  Print the structured output of the prediction
    res.save_to_img(save_path="output") ## Save the formula visualization result of the current image.
    res.save_to_json(save_path="output") ## Save the structured JSON result of the current image
```

For details about usage command and descriptions of parameters, please refer to the [Document](https://paddlepaddle.github.io/PaddleOCR/latest/en/version3.x/pipeline_usage/formula_recognition.html#2-quick-start).

#### PP-StructureV3

Layout analysis is a technique used to extract structured information from document images. PP-StructureV3 includes the following six modules:
* Layout Detection Module
* General OCR Subline
* Document Image Preprocessing Subline （Optional）
* Table Recognition Subline （Optional）
* Seal Recognition Subline （Optional）
* Formula Recognition Subline （Optional）

Run a single command to quickly experience the PP-StructureV3 pipeline:

```bash
paddleocr pp_structurev3 --formula_recognition_model_name PP-FormulaNet_plus-L -i https://cdn-uploads.huggingface.co/production/uploads/68493f0616e67d38f02f138a/bar8SvxUbAFdMmIMyZpTk.png
```

Just a few lines of code can experience the inference of the pipeline. Taking the PP-StructureV3 pipeline as an example:

```python
from paddleocr import PPStructureV3

pipeline = PPStructureV3(
    formula_recognition_model_name="PP-FormulaNet_plus-L",
    use_doc_orientation_classify=False,   # Use use_doc_orientation_classify to enable/disable document orientation classification model
    use_doc_unwarping=False, # Use use_doc_unwarping to enable/disable document unwarping module
    use_textline_orientation=False, # Use use_textline_orientation to enable/disable textline orientation classification model
    device="gpu:0", # Use device to specify GPU for model inference
    )
output = pipeline.predict("./bar8SvxUbAFdMmIMyZpTk.png")
for res in output:
    res.print() # Print the structured prediction output
    res.save_to_json(save_path="output") ## Save the current image's structured result in JSON format
    res.save_to_markdown(save_path="output") ## Save the current image's result in Markdown format
```

The default model used in pipeline is `PP-FormulaNet_plus-L`. And you can also use the local model file by argument `formula_recognition_model_dir`. For details about usage command and descriptions of parameters, please refer to the [Document](https://paddlepaddle.github.io/PaddleOCR/latest/en/version3.x/pipeline_usage/PP-StructureV3.html#2-quick-start).

## Links

[PaddleOCR Repo](https://github.com/paddlepaddle/paddleocr)

[PaddleOCR Documentation](https://paddlepaddle.github.io/PaddleOCR/latest/en/index.html)
