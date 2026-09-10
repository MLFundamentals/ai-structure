# notebooks/

구글 드라이브 원본의 사본을 이곳에 둔다. 파일명은 `notebooks.yml` 의
`file` 값과 같아야 한다.

| 쪽 | 파일 | 비고 |
|---|---|---|
| 60 | `Linear_Regression.ipynb` | 수치 검사 있음 (수렴) |
| 73 | `MNIST_Softmax.ipynb` | |
| 85 | `XOR_perceptron.ipynb` | **판정 방향 반대 — 성공하면 경보** |
| 103 | `MNIST_CNN.ipynb` | |
| 108 | `RNN.ipynb` | 끝에 `input()` 루프 |
| 220 | `LLM.ipynb` | 무겁다. CPU 에서 10~20분 |

188쪽은 GIF 그림이라 사본이 없다. 링크 점검만 한다.

**⚠ 파일명을 바꾸지 말 것.** Colab 원본 이름 그대로다. Colab 의
"GitHub 에 사본 저장"이 이 이름으로 덮어쓰기 때문에, 여기서 이름을
바꾸면 다음 저장 때 원래 이름으로 파일이 하나 더 생기고 이름을 바꿔
둔 쪽이 낡은 사본으로 남는다.

**드라이브 원본을 고치면 이 사본도 반드시 함께 고친다.**
검증 셀을 추가하지 말 것 — 판정은 `checks/verify_results.py` 가
실행 결과를 바깥에서 읽어 한다.
