# LLM 경로 · 공공데이터 검증 노트 (feat/verify-llm-and-public-data)

작성: 2026-08-28. 대상: `allnew` @ `8362cb6`.
**코드는 새 파일만 추가한다. 기존 파일·docs·steering 은 건드리지 않는다 (병합 안전).**

## 왜 이 브랜치인가

`.kiro/steering/tech-constraints.md §5` — "로컬 MOCK 통과를 신뢰하지 말 것". MOCK은
Bedrock 요청 형식도, 판단도 흉내 못 낸다. 실제로 두 번 당했다(`temperature` 거부,
thinking 블록). 로컬에서 **이 부류를 잡는 안전망**과, **공공데이터가 실제로 쓸모 있는지**를
측정할 도구가 없었다. 이 브랜치가 그 둘을 추가한다.

## 추가한 것 (전부 신규 파일)

| 파일 | 하는 일 |
|---|---|
| `tests/test_bedrock_contract.py` | boto3 가짜로 바꿔 `verdict_service`·`parse_service`가 **실제 조립하는 요청 body**를 검사: `temperature`/`top_p` 없음, 모델 ID `global.` 접두사, region 코드 미지정, thinking 블록 뒤 text 파싱, text 없을 때 폴백 |
| `tests/test_public_data_index.py` | 합성 상가정보 CSV → `build_store_index` → `store_lookup` → `refine_categories` **전 경로**를 실제로 돌려 카테고리 보정 동작 확인 (실 색인 129MB 없이) |
| `tests/test_analysis_integration.py` | 격리된 임시 DB로 `GET /api/analysis` 전체: 응답 키 15개, TRANSFER 총지출 제외, benchmark 방향·출처, remark 발화, plea 정상참작 evidence 반영 |
| `scripts/smoke_bedrock.py` | **배포 서버에서** 실 Bedrock 1회씩 호출 → 이유·형량·정규화 출력, 폴백이면 exit 1 |
| `scripts/measure_public_data_value.py` | 상호명 리스트에 대해 (키워드 / 공공데이터 구제 / 끝까지 OTHER) 집계. 서버는 실 색인, 로컬은 `--mini` 합성 색인 |

기존 테스트 32건 + 신규 30건 = **62 passed (skipped 6: 실 색인 필요 테스트)**.

## LLM 출력 품질 — 로컬에서 확인 불가

자격증명이 없어 로컬 Bedrock 호출은 항상 실패한다(정상, steering 지침). 그래서
**판결문·카테고리 자동화의 실제 품질은 배포 후에만** 볼 수 있다. 확인 절차:

```
# EC2
appenv/bin/python scripts/smoke_bedrock.py        # 폴백 여부 + 출력 육안 확인
grep -c "Bedrock 호출 실패" app.log               # 0 이어야 정상
```

로컬에서 보장하는 것은 **요청이 규격에 맞는다**(위 계약 테스트)와 **응답 파싱·폴백이
정상**이라는 것까지다.

## 공공데이터가 유용한가

두 종류가 있고 성격이 다르다.

### 1. 상권정보 색인 (카테고리 보정) — **유용. 단, 잔여분에만.**

`measure_public_data_value.py --mini` 표본 23건 결과:
- 키워드 규칙이 65% 를 이미 분류 (프랜차이즈는 키워드로 충분)
- 공공데이터가 17% 추가 구제 (독립·로컬 상호: "행복한과일가게", "초록마을유기농" 등)
- 17% 는 끝까지 OTHER (사람 이름 송금 — 어차피 사용자 정리 대상)

즉 **키워드로 안 잡히는 독립 상호에서만 값어치가 있다.** 프랜차이즈 위주 내역이면
기여가 거의 0. 실제 기여도는 서버에서 진짜 색인 + 진짜 거래내역으로 재측정해야 한다
(`scripts/measure_public_data_value.py --names <실거래상호.txt>`).

**권장**: 색인이 없어도 앱은 정상 동작하므로(조용히 비활성), 데모에서 독립 상호가
섞인 샘플 파일을 하나 준비해 "공공데이터로 잡았다"를 보여주는 게 효과적이다.

### 2. 1인가구 벤치마크 (`benchmark`) — **동작하지만 해석 주의.**

`benchmark_data.py` 의 `TOTAL_MONTHLY = 1,689,000` 은 **주거·교통·통신·보건까지 포함한
1인가구 전체 소비지출**이다. 이 앱은 재량 소비 6종만 추적하므로 시드 전 월이
"평균보다 한참 적게 썼다"로 나온다(총액 비교 `totalDiffPercent` 기준).

- 카테고리별 비교(`diffPercent`, `headline`)는 상대적으로 덜 왜곡됨 — 시드 2026-08
  배달 100,000원 vs 기준 246,000원 → "28% 적게" 는 납득 가능.
- 총액 비교는 사과-오렌지다. 프론트가 `headline`(카테고리)만 띄우고 총액 비교는
  숨기거나 약하게 다루는 편이 정직하다. `isEstimated: true` 표기는 이미 있음.
- `benchmark_data.py` 주석의 TODO(29세 이하 수치로 교체)가 해결되면 훨씬 자연스러워짐.

## 검토 중 발견한 것 (백엔드 동결 — 수정 안 함, 팀 판단용)

1. **`store_lookup._strip_branch` 정규식 과다 매칭.**
   `_BRANCH_SUFFIX = (본점|직영점|[0-9a-z가-힣]{2,10}점)$` 가 탐욕적이라
   "왕곱창막창홍대점" → "왕" 만 남긴다("점" 앞 최대 10자를 통째 제거). 지점 표기
   1회 제거 의도인데 상호 본체까지 먹는다. 상호에 "편의점"·"..점" 이 들어가면 특히.
   영향은 제한적 — exact 매칭(전체 이름)이 먼저 걸리는 경우가 대부분이고, 이건
   그 다음 폴백 단계다. 색인이 클수록 노출 확률 낮음.
   *제안*: `[가-힣]{2,4}(점|지점)$` 처럼 비탐욕 + 길이 축소, 또는 stripped 결과가
   2자 미만이면 원본 유지(현재는 그렇게 함 — 그래서 완전히 죽지는 않는다).

2. **규칙 폴백의 사람이름 송금 오분류.** (steering §5 에 이미 기록됨)
   `parse_service` 규칙 폴백은 "토스뱅크 김민수" 를 `OTHER`/`EXPENSE`/`needsReview=false`
   로 넣는다. Bedrock 은 `TRANSFER` 로 본다. Bedrock 이 살아있으면 비이슈지만,
   폴백일 때 이 돈이 총지출·유형 판정에 섞인다. `remark` 는 이체까지 세므로 그쪽은 OK.

## 다음 (사람이 서버에서)

```
scp store_category.sqlite → EC2:data/                    # 색인 없으면 보정 비활성
appenv/bin/python scripts/smoke_bedrock.py               # LLM 살아있나
appenv/bin/python scripts/measure_public_data_value.py   # 공공데이터 기여도 실측
```
