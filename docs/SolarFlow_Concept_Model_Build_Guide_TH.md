# SolarFlow AI — คู่มือออกแบบโมเดลแนวคิด V1

| รายการ | ข้อกำหนด |
|---|---|
| ประเภท | โมเดลอธิบายแนวคิดแบบตั้งโต๊ะ |
| วัตถุประสงค์ | แสดงการเพิ่ม active optical layer และ release primer บนแผงเดิม |
| สถานะ | Conceptual model — not to scale |
| ไม่ใช่ | Functional prototype หรือผลทดสอบเพิ่มกำลังไฟจริง |
| Visual หลัก | `docs/assets/solarflow_concept_model_exploded.svg` |

---

## 1. แนวทางที่เลือก

โมเดล V1 ใช้รูปแบบ **มุมแผงโซลาร์เซลล์แบบตัดขวางและแยกชั้น** หรือ
`exploded optical stack` เนื่องจากสามารถอธิบายได้ภายในไม่กี่วินาทีว่า
SolarFlow เพิ่มอะไรเข้าไปบนแผงเดิม และส่วนใดเป็นข้อมูลที่ยังต้องวัดจริง

โมเดลต้องสื่อสารสามประเด็นพร้อมกัน:

1. ไม่ต้องเปลี่ยนแผงหลักทั้งชุด
2. แนวคิดปัจจุบันเป็น direct coating ไม่ใช่แผ่น carrier film
3. ผลที่มีเป็น simulation/proxy evidence ไม่ใช่ prototype performance

---

## 2. รูปร่างโดยรวม

ขนาดแนะนำ:

```text
ฐานโมเดล: 45 × 30 cm
พื้นที่แผงจำลอง: ประมาณ 25 × 18 cm
ความสูงรวม: ไม่เกิน 25 cm
มุมเอียงของแผง: 10–15°
พื้นที่ป้ายผลและ QR code: ด้านขวาประมาณ 15 × 25 cm
```

การจัดวาง:

```text
┌─────────────────────────────────────────────┐
│ แสง / ลูกศร      Exploded layer labels     │
│                                             │
│      Active layer                          │
│      Release primer        Result + QR      │
│      Factory AR            Limitations      │
│      Cover glass                            │
│      Solar cell / panel                     │
└─────────────────────────────────────────────┘
```

ใช้ฐานสีน้ำเงินเข้มหรือเขียวเข้มเพื่อเชื่อมกับพลังงานสะอาดและบริบทโซลาร์
ลอยน้ำ แต่ต้องให้ชั้นวัสดุและข้อความมี contrast สูง

---

## 3. รายการวัสดุสำหรับโมเดลแสดงแนวคิด

วัสดุทั้งหมดใช้เพื่อการสื่อสาร ไม่ได้แทนวัสดุจริงในแบบจำลอง

| ส่วน | วัสดุทำโมเดลที่แนะนำ | หมายเหตุ |
|---|---|---|
| ฐาน | ฟิวเจอร์บอร์ด กระดาษลูกฟูกแข็ง หรือ foam board 5 mm | เลือกวัสดุใช้ซ้ำได้ถ้าเป็นไปได้ |
| แผงจำลอง | ภาพพิมพ์เซลล์แสงอาทิตย์ติดบนบอร์ด หรือแผงขนาดเล็กที่ไม่ได้ใช้วัดผล | ห้ามสาธิตตัวเลข performance จากแผงนี้ |
| Cover glass | แผ่นอะคริลิกใสหรือ PET ใสจากบรรจุภัณฑ์ | ทำเป็นชั้นหนาเพื่อให้เห็นง่าย |
| Factory AR | ฟิล์มใสสีเหลืองอ่อน | ติดป้าย `ASSUMED` ชัดเจน |
| Release primer | ฟิล์มใสสีเขียวอ่อน | เป็นตัวแทนเชิงภาพเท่านั้น |
| Active layer | ฟิล์มใสสีฟ้าหรือ cyan | ให้บางที่สุดเมื่อเทียบกับชั้นอื่น |
| ตัวเว้นระยะ | แท่งอะคริลิก ไม้เสียบ หรือน็อต spacer | ใช้แยกชั้นให้เห็น exploded view |
| ลูกศรแสง | ลวดสีเหลือง/เขียว หรืออะคริลิกตัดรูป | เหลือง = incident, เขียว = transmitted |
| ป้าย | กระดาษการ์ดพิมพ์หรือสติกเกอร์ | ใช้ข้อความจากส่วนที่ 5 |

หากใช้แผ่นพลาสติกใสหลายชั้น ต้องติดป้ายว่าเป็นวัสดุทำโมเดล เพราะการเพิ่ม
carrier film จริงสามารถเปลี่ยนผลทางแสงและไม่ใช่สถาปัตยกรรมที่ล็อกใน Phase 1.6

---

## 4. ลำดับชั้นและสี

| ลำดับจากด้านบน | ชั้น | สีในโมเดล | ข้อมูลที่แสดง |
|---:|---|---|---|
| 1 | Active optical layer | Cyan | `n=1.092934, d=116.736 nm — modeled target` |
| 2 | Release primer | เขียวอ่อน | `n=1.20, d=50 nm — generic modeled interface` |
| 3 | Factory AR | เหลืองอ่อน | `n=1.28, d=100 nm — assumed` |
| 4 | Cover glass | ฟ้าใส | `n=1.52 — representative` |
| 5 | Solar cell/module | น้ำเงินเข้ม | `Existing JA Solar family reference` |

ทุกชั้นต้องมีเส้นชี้จากชิ้นงานไปยังป้ายกำกับ หลีกเลี่ยงการเขียนค่าตัวเลขลงบน
ชิ้นงานโดยตรงเพราะจะอ่านยากเมื่อถ่ายวิดีโอ

---

## 5. ป้ายข้อความที่ต้องมี

### ป้ายบนสุด

```text
SOLARFLOW RETROFIT OPTICAL STACK
Conceptual model — not to scale
```

### ป้ายแยกขอบเขต

```text
SOLARFLOW RETROFIT
Active optical layer + release primer
```

```text
EXISTING MODULE
Factory AR + cover glass + solar cells
```

### ป้ายผลจำลอง

```text
Nominal optical model: +0.6667%
Measured-SR proxy weighting: approximately +0.814%
Conditional simulation results — not measured module power
```

### ป้ายข้อจำกัด

```text
Measurement required:
- actual factory AR n(lambda), k(lambda), thickness
- target-module EQE/SR and I-V
- candidate material optical and durability data
```

### ป้าย topcoat

```text
Protective topcoat is not included in the current stack.
Protection must be redesigned and validated separately.
```

---

## 6. ขั้นตอนประกอบ

1. ตัดฐานขนาดประมาณ `45 × 30 cm` และหุ้มด้วยกระดาษสีพื้น
2. ทำแผงจำลองขนาดประมาณ `25 × 18 cm` พร้อมลายเซลล์
3. ยกแผงให้เอียง `10–15°` ด้วยฐานสามเหลี่ยมหรือขาตั้งด้านหลัง
4. ตัดแผ่นใสสำหรับ glass, AR, primer และ active layer
5. ใช้ spacer แยกชั้นให้ระยะห่างพอสำหรับการมองและถ่ายวิดีโอ
6. จัดชั้นตามลำดับ active → primer → AR → glass → solar cell
7. ติดลูกศร incident light สีเหลืองและ transmitted light สีเขียว
8. ติดป้ายแยก `SolarFlow retrofit` และ `Existing module`
9. วางผลจำลองและคำเตือนด้านขวาของฐาน
10. เพิ่ม QR code ไปยัง GitHub หรือ Phase 1.6 Research Record
11. ถ่ายรูปจากด้านหน้า ด้านข้าง และมุม 45° เพื่อตรวจความอ่านง่าย

ชั้นต่าง ๆ ถูกขยายความหนาเพื่อให้มองเห็นได้ จึงต้องมีคำว่า `not to scale`
ตลอดเวลา

---

## 7. สิ่งที่ไม่ควรทำ

- อย่าใส่ protective topcoat ในโมเดลปัจจุบัน
- อย่าแสดง active layer เป็นแผ่นฟิล์มหนาและเรียกว่าโครงสร้างผลิตภัณฑ์จริง
- อย่าใส่ LED หรือมิเตอร์ที่แสดงว่ากำลังไฟเพิ่ม หากไม่ได้มาจากการทดลองจริง
- อย่าติดป้าย `+0.814% power gain`
- อย่าใช้คำว่า waterproof, durable, warranty-safe หรือ field-ready
- อย่าให้โมเดลดูเหมือนต้องเปลี่ยนกระจกหรือเซลล์ของแผงเดิม
- อย่าใช้ลูกศรที่สื่อว่าแสงหรือพลังงานถูกสร้างเพิ่มขึ้นเอง

---

## 8. วิธีสาธิตต่อกรรมการ

ลำดับการอธิบายประมาณ 45 วินาที:

> ส่วนล่างนี้คือแผงเดิมที่มี solar cell, cover glass และ factory AR ซึ่งค่า
> optical stack จริงยังต้องวัดเพิ่มเติม แนวคิด SolarFlow เพิ่มเพียง release
> primer และ active optical layer ดัชนีต่ำบนผิวหน้า เพื่อปรับการสะท้อนและเพิ่ม
> แสงที่ส่งผ่านเข้าสู่เซลล์ ผล nominal ในแบบจำลองเชิงแสงอยู่ที่ประมาณ 0.667%
> และเมื่อถ่วงด้วย measured spectral-response proxy สามชุดได้ประมาณ 0.814%
> แต่โมเดลชิ้นนี้เป็นสื่ออธิบายแนวคิด ไม่ใช่ prototype ที่วัดกำลังไฟแล้ว ขั้น
> ต่อไปจึงเป็นการตรวจวัสดุ optical stack, EQE/SR, I-V และความทนทานจริง

ให้ชี้โมเดลตามลำดับจากล่างขึ้นบน แล้วจบที่ป้ายข้อจำกัด การอธิบายข้อจำกัดเอง
ช่วยแสดงให้เห็นว่าทีมควบคุมขอบเขตงานวิจัย ไม่ใช่จุดอ่อนที่ต้องซ่อน

---

## 9. ภาพสำหรับสไลด์และวิดีโอ

ไฟล์หลัก:

```text
docs/assets/solarflow_concept_model_exploded.svg
docs/assets/solarflow_concept_model_exploded.png
```

แนะนำให้ใช้ SVG ในสไลด์หากโปรแกรมรองรับ เพราะขยายแล้วไม่แตก ส่วน PNG ใช้ใน
โปรแกรมตัดต่อวิดีโอหรือช่องทางที่ไม่รองรับ SVG

Animation ที่ทำต่อได้:

1. แสดง existing module ก่อน
2. เลื่อน release primer ลงมาเหนือ factory AR
3. เลื่อน active layer ลงมาเป็นชั้นบนสุด
4. แสดงลูกศร incident/reflected/transmitted light
5. แสดงผล nominal พร้อมคำว่า `conditional model`
6. ปิดด้วย measurement-required checklist

---

## 10. Acceptance checklist

ก่อนล็อกโมเดล V1 ต้องผ่านทุกข้อ:

- [ ] ลำดับชั้นตรงกับ Phase 1.6 source-of-truth stack
- [ ] มีคำว่า `Conceptual model — not to scale`
- [ ] ไม่มี protective topcoat หรือ carrier film ในโครงสร้างจริงที่อธิบาย
- [ ] Factory AR ถูกระบุว่า assumed/measurement required
- [ ] ค่า `+0.814%` ถูกเรียกว่า relative photocurrent-proxy ไม่ใช่ power gain
- [ ] อ่านป้ายหลักได้จากระยะประมาณ 1–2 เมตร
- [ ] ภาพถ่ายแนวตั้งและแนวนอนยังเห็นลำดับชั้นชัดเจน
- [ ] QR code เชื่อมไปยังเอกสารหรือ repository ที่เปิดได้
- [ ] ไม่มีการอ้าง durability, safety, warranty หรือ field performance
- [ ] ทีมทุกคนใช้คำอธิบายตัวเลขชุดเดียวกัน

เมื่อ checklist ผ่าน โมเดล V1 จึงพร้อมเป็น visual source-of-truth สำหรับสไลด์
10 หน้าและวิดีโอ 1 ชิ้น
