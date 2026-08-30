# Preliminary Optical Simulation Results

## SolarFlow AI — Retrofit Optical Layer for Existing Solar Panels

**Status:** Preliminary simulation  
**Competition track:** Circular Innovation  
**Target application:** Existing floating photovoltaic panels  
**Example context:** Sirindhorn Dam floating solar farm  
**Date:** 30 August 2026

---

## 1. Project Objective

โครงการนี้ศึกษาความเป็นไปได้ของวัสดุหรือชั้นฟิล์มที่สามารถติดตั้งเพิ่มเติมบนแผงโซลาร์เซลล์เดิม เพื่อเพิ่มปริมาณแสงที่ส่งผ่านเข้าสู่ตัวเซลล์ โดยไม่จำเป็นต้องซื้อหรือเปลี่ยนแผงโซลาร์เซลล์ใหม่ทั้งหมด

แนวคิดนี้มีความเกี่ยวข้องกับ Circular Economy ในด้าน:

- การเพิ่มประสิทธิภาพของสินทรัพย์เดิม
- การลดความจำเป็นในการผลิตและซื้อแผงใหม่
- การยืดอายุการใช้งานเชิงเศรษฐกิจของระบบเดิม
- การออกแบบวัสดุ retrofit ที่สามารถถอดเปลี่ยนได้

การศึกษารอบนี้เป็นการจำลองด้าน optical transmission เท่านั้น ยังไม่ใช่การยืนยันกำลังไฟฟ้าจริงของแผง

---

## 2. Research Question

ชั้นวัสดุโปร่งใสที่ติดตั้งเพิ่มเติมบนกระจกของแผงโซลาร์เซลล์เดิม สามารถลดการสะท้อนและเพิ่มปริมาณแสงที่ส่งผ่านได้หรือไม่ เมื่อแผงเดิมอาจมี anti-reflection coating อยู่แล้ว

---

## 3. Simulation Architecture

โมเดลหลักที่ใช้ในการศึกษาเป็นโครงสร้างแบบหลายชั้น:

```text
Air
→ Retrofit optical layer
→ Existing anti-reflection coating
→ Solar-panel cover glass
```

ค่าตัวแทนของแผงเดิม:

| Parameter | Value |
|---|---:|
| Air refractive index | 1.00 |
| Existing AR refractive index | 1.28 |
| Existing AR thickness | 100 nm |
| Glass refractive index | 1.52 |
| Wavelength range | 300–1200 nm |
| Initial angle of incidence | 0° |

ค่า existing AR เป็น representative baseline จากช่วงค่าที่พบในงานด้าน porous-silica AR coating และยังไม่ได้รับการยืนยันว่าเป็นสเปกจริงของแผงที่เขื่อนสิรินธร

---

## 4. Tools and Their Roles

### Meep

ใช้ Finite-Difference Time-Domain หรือ FDTD เพื่อจำลองการแพร่ การสะท้อน และการส่งผ่านของคลื่นแม่เหล็กไฟฟ้า

### Transfer Matrix Method

ใช้เป็น solver ที่รวดเร็วสำหรับโครงสร้างฟิล์มเรียบหลายชั้น และใช้ตรวจสอบผลร่วมกับ Meep

### Solcore

ใช้ข้อมูลสเปกตรัมแสงอาทิตย์มาตรฐาน AM1.5G เพื่อคำนวณ solar-weighted optical transmission ในช่วง 300–1200 nm

### Optuna

ใช้ Tree-structured Parzen Estimator หรือ TPE เพื่อค้นหา refractive index และความหนาของชั้น retrofit ที่ให้ transmitted optical power สูงที่สุด

Optuna ในโครงการนี้ทำหน้าที่เป็น model-based optimization หรือ AI-assisted parameter search ไม่ใช่ Generative AI

---

## 5. Baseline Verification

### 5.1 Bare Air-to-Glass Interface

Meep ถูกตรวจสอบกับสมการ Fresnel สำหรับรอยต่ออากาศกับกระจก

| Metric | Result |
|---|---:|
| Analytic Fresnel reflectance | 4.2580% |
| Mean Meep reflectance | 4.1954% |
| Mean Meep transmittance | 95.8056% |
| Maximum Fresnel error | 1.429 × 10⁻³ |
| Maximum energy residual | 8.718 × 10⁻⁴ |

ผลการ convergence test สำหรับหลายค่า resolution ผ่าน tolerance ที่กำหนด

### 5.2 Ideal Quarter-Wave Film

สร้าง ideal single-layer AR film สำหรับกระจกเปล่า:

| Parameter | Value |
|---|---:|
| Film refractive index | 1.232883 |
| Film thickness | 111.527 nm |
| Design wavelength | 550 nm |
| Reflectance near design wavelength | approximately 0% |
| Transmittance near design wavelength | approximately 99.9999% |
| Maximum analytic error | 2.358 × 10⁻⁴ |
| Maximum energy residual | 7.277 × 10⁻⁴ |

กรณีนี้เป็น theoretical optical upper bound ไม่ใช่วัสดุ final ที่ยืนยันแล้วว่าสามารถผลิตได้

---

## 6. AM1.5G-Weighted Baseline Comparison

ผลการถ่วงด้วยสเปกตรัมแสงอาทิตย์ AM1.5G:

| Optical configuration | Weighted transmittance | Transmitted power | Relative gain vs bare glass |
|---|---:|---:|---:|
| Bare glass | 95.7790% | 800.791 W/m² | 0.0000% |
| Existing AR, 100 nm | 98.9638% | 827.418 W/m² | 3.3251% |
| Existing AR, 180 nm | 98.1418% | 820.546 W/m² | 2.4669% |
| Ideal flat film | 99.1425% | 828.912 W/m² | 3.5117% |

Ideal film มี optical headroom เหนือ existing AR 100 nm เพียงประมาณ 0.1806%

ผลนี้แสดงว่า หากแผงเดิมมี AR coating ที่มีประสิทธิภาพอยู่แล้ว พื้นที่สำหรับเพิ่มการส่งผ่านแสงด้วยฟิล์มเรียบชั้นเดียวจะเหลือไม่มาก

---

## 7. Naive Stacked Retrofit Test

มีการทดสอบนำ ideal quarter-wave film ที่ออกแบบสำหรับกระจกเปล่าไปติดซ้อนบน existing AR โดยตรง

```text
Air
→ Ideal quarter-wave film
→ Existing AR
→ Glass
```

ผลลัพธ์:

| Metric | Result |
|---|---:|
| Existing AR transmitted power | 827.445 W/m² |
| Naive stacked transmitted power | 824.555 W/m² |
| Additional transmitted power | -2.890 W/m² |
| Relative optical gain | -0.3493% |
| Maximum Meep–TMM error | 2.365 × 10⁻⁴ |

ผลแสดงว่าฟิล์มที่เหมาะกับกระจกเปล่าไม่สามารถนำมาติดซ้อนบน AR เดิมได้โดยตรง เพราะ interference ระหว่างชั้นสามารถทำให้ประสิทธิภาพลดลง

ดังนั้น retrofit layer ต้องถูกออกแบบร่วมกับ existing coating ตั้งแต่ต้น

---

## 8. AI-Assisted Optimization

Optuna TPE ถูกใช้เพื่อค้นหา parameter ของ homogeneous flat retrofit layer โดยแบ่งเป็นสอง search spaces

### 8.1 Practical Polymer-Like Film

| Parameter | Optimized result |
|---|---:|
| Refractive index | 1.300000 |
| Thickness | 20.000 nm |
| Additional optical power | 0.324 W/m² |
| Relative gain | 0.0392% |

ค่าที่ดีที่สุดชนขอบต่ำสุดของทั้ง refractive index และ thickness แสดงว่า optimizer ต้องการให้ชั้น polymer บางและมี index ต่ำที่สุด

ผลเพิ่มขึ้นเพียงเล็กน้อยและอยู่ใกล้ระดับ numerical uncertainty จึงยังไม่ถือเป็น candidate ที่แข็งแรง

### 8.2 Engineered Low-Index Layer

| Parameter | Optimized result |
|---|---:|
| Refractive index | 1.100474 |
| Thickness | 118.791 nm |
| Transmitted power | 833.382 W/m² |
| Additional optical power | 5.936 W/m² |
| Absolute optical gain | 0.7100 percentage points |
| Relative optical gain | 0.7174% |

ผลนี้ไม่ได้ชนขอบของ search space และมี gain สูงกว่าความคลาดเคลื่อนของ baseline อย่างชัดเจน จึงถูกเลือกเป็น candidate สำหรับการตรวจสอบด้วย Meep

ค่า refractive index ประมาณ 1.10 ต่ำกว่าวัสดุ polymer เนื้อแน่นทั่วไป Candidate นี้จึงน่าจะต้องอาศัย:

- Porous material
- Effective-medium structure
- Subwavelength microtexture
- Nanostructured or moth-eye-like surface

ความสามารถในการผลิต ความทนทาน และผลกระทบจากน้ำหรือความชื้นยังไม่ได้รับการยืนยัน

---

## 9. Meep Validation of Optimized Candidate

Candidate จาก Optuna ถูกจำลองด้วย Meep โดยเปรียบเทียบ:

```text
Case A:
Air → Existing AR → Glass

Case B:
Air → Optimized retrofit → Existing AR → Glass
```

ใช้ reference normalization และ incident-field subtraction แบบเดียวกันทั้งสองกรณี

### 9.1 Resolution 200 Results

| Metric | Result |
|---|---:|
| Existing AR power | 827.436 W/m² |
| Optimized stacked power | 833.332 W/m² |
| Additional optical power | 5.896 W/m² |
| Meep relative gain | 0.7126% |
| TMM relative gain | 0.7174% |
| Gain difference | 0.0049% |

### 9.2 Resolution 300 Results

| Metric | Result |
|---|---:|
| Existing AR power | 827.470 W/m² |
| Optimized stacked power | 833.497 W/m² |
| Additional optical power | 6.027 W/m² |
| Absolute optical gain | 0.7209 percentage points |
| Meep relative gain | 0.7284% |
| TMM relative gain | 0.7174% |
| Gain difference | 0.0109% |
| Maximum existing TMM error | 9.309 × 10⁻⁵ |
| Maximum stacked TMM error | 1.071 × 10⁻⁴ |
| Maximum existing energy residual | 1.891 × 10⁻³ |
| Maximum stacked energy residual | 4.156 × 10⁻³ |

ค่า optical gain ของ Meep และ TMM สอดคล้องกันมาก และผล gain ยังคงอยู่เมื่อเพิ่ม resolution จาก 200 เป็น 300

อย่างไรก็ตาม maximum pointwise energy residual ของ stacked case ที่ resolution 300 ยังสูงกว่า tolerance 2 × 10⁻³ ที่ตั้งไว้ ส่งผลให้ automated validation flag ยังคงเป็น `false`

จึงสรุปสถานะได้ว่า:

> Candidate ผ่านการตรวจสอบด้านแนวโน้มและ solar-weighted optical gain ระหว่าง independent solvers แต่ยังไม่ผ่าน strict maximum pointwise energy-conservation criterion และต้องได้รับ numerical convergence study เพิ่มเติมในระยะถัดไป

ไม่มีการแก้ tolerance เพื่อบังคับให้ผล validation เป็น `true`

---

## 10. Preliminary Conclusion

ผลการจำลองเบื้องต้นสนับสนุนว่า retrofit optical layer อาจเพิ่มปริมาณแสงที่ส่งผ่านแผงเดิมที่มี AR coating อยู่แล้วได้ หากสามารถสร้างชั้นที่มี effective refractive index ต่ำประมาณ 1.10 และควบคุมความหนาได้ประมาณ 119 nm

ผลที่ได้จาก Meep อยู่ในช่วง:

```text
ประมาณ +0.71% ถึง +0.73% relative optical gain
```

หรือประมาณ:

```text
+5.9 ถึง +6.0 W/m² transmitted optical power
```

ภายใต้ AM1.5G ช่วง 300–1200 nm และมุมตกกระทบ 0°

ผลนี้ยังไม่สามารถตีความเป็น electrical power gain เท่ากันโดยตรง และยังไม่ควรนำไปคูณกับกำลังติดตั้งของโรงไฟฟ้า

---

## 11. Current Limitations

1. Existing AR coating เป็น representative assumption ไม่ใช่สเปกจริงที่ยืนยันจากผู้ผลิตแผง
2. Refractive indices ถูกสมมติเป็นค่าคงที่และไม่มี material dispersion
3. จำลองเฉพาะ normal incidence ที่ 0°
4. ยังไม่มี TE/TM polarization และ angle sweep
5. ยังไม่มีการจำลอง absorption และ scattering loss ของวัสดุจริง
6. ยังไม่มี adhesive layer หรือ microscopic air gap
7. ยังไม่มี surface roughness และ manufacturing tolerance
8. ยังไม่มีผลจากฝุ่น น้ำ ความชื้น ความร้อน และการเสื่อมสภาพ
9. ยังไม่มี electrical solar-cell model สำหรับแปลง optical gain เป็น electrical gain
10. ยังไม่มี laboratory หรือ field validation
11. Strict maximum energy-residual validation ยังไม่ผ่านใน Meep stacked case

---

## 12. Recommended Next Phase

### Phase 2A — Numerical Validation

- ตรวจ wavelength ที่เกิด maximum residual
- ทำ convergence study เพิ่มเติม
- ตรวจ source, monitor และ PML configurations
- เปรียบเทียบ solar-weighted error แทนการพิจารณาเฉพาะ maximum pointwise error

### Phase 2B — Manufacturable Optical Design

- เพิ่ม material dispersion จากข้อมูลจริง
- เพิ่ม polymer carrier และ adhesive layer
- กำหนด manufacturing constraints
- วิเคราะห์ porosity และ effective refractive index
- ออกแบบ microtexture หรือ graded-index structure

### Phase 2C — Operating Conditions

- Angle-of-incidence sweep
- TE/TM polarization
- Floating-panel temperature
- Humidity and water ingress
- Soiling and cleaning
- Mechanical durability

### Phase 2D — Electrical and Circular Assessment

- ส่ง optical spectrum เข้า Solcore solar-cell model
- คำนวณ current, voltage, efficiency และ electrical power
- ประเมินอายุการใช้งาน
- ประเมินต้นทุนและระยะเวลาคืนทุน
- เปรียบเทียบ material use กับการซื้อแผงใหม่
- ทำ preliminary life-cycle and circularity assessment

---

## 13. Reproducibility

Environment หลัก:

| Software | Version |
|---|---:|
| Python | 3.11 |
| Meep | 1.34.0 |
| Solcore | 5.10.1 |
| Optuna | 4.9.0 |
| Platform | Ubuntu 24.04 on WSL2 |

Environment name:

```bash
conda activate solarflow-full
```

Core scripts:

```text
product1/meep/baseline_glass.py
product1/meep/run_baseline_convergence.py
product1/meep/flat_film.py
product1/meep/representative_existing_ar.py
product1/analysis/stacked_retrofit_tmm.py
product1/optimizer/optimize_flat_retrofit.py
product1/meep/validate_optimized_stack.py
product1/solcore/solar_weighted_optics.py
product1/solcore/compare_optical_baselines.py
```

Core result figures:

```text
product1/results/figures/bare_glass_vs_ideal_flat_film.png
product1/results/figures/am15g_transmitted_optical_power.png
product1/results/figures/am15g_optical_baseline_comparison.png
product1/results/figures/stacked_retrofit_tmm.png
product1/results/figures/optimized_stack_meep_validation.png
```

---

## 14. References

- Meep: https://github.com/NanoComp/meep
- Meep documentation: https://meep.readthedocs.io/
- Solcore: https://github.com/qpv-research-group/solcore5
- Solcore documentation: https://docs.solcore.solar/
- DEVSIM: https://github.com/devsim/devsim
- Optuna: https://optuna.org/
- Project context: `docs/egat_context.md`

---

## 15. Preliminary Deliverable Status

The current repository contains:

- Reproducible optical baselines
- Fresnel and TMM verification
- AM1.5G-weighted comparison
- Negative control for naive retrofit stacking
- AI-assisted parameter optimization
- Independent Meep validation
- Machine-readable CSV and JSON results
- Generated figures
- Documented assumptions and limitations

This deliverable is suitable as a preliminary simulation and design-screening result. It is not yet a validated commercial product design or field-performance claim.
