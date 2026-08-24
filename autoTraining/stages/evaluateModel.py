"""기존·후보 모델 비교 평가 단계를 외부에서 호출하기 위한 얇은 어댑터입니다.

실제 처리 로직과 상태는 trainingPipeline.TrainingPipeline이 소유합니다.
이 파일은 오케스트레이터가 각 단계를 명시적인 함수로 연결할 수 있게 해 줍니다.
단계별 파일을 분리하면 나중에 테스트, 작업 큐, 스케줄러 또는 별도 컨테이너가
메인 클래스의 내부 구현을 알지 않고도 같은 진입점을 호출할 수 있습니다.
"""

from typing import Protocol


class PipelineContext(Protocol):
    """이 단계가 요구하는 최소 메서드만 선언한 구조적 타입입니다.

    Protocol은 실제 객체를 생성하지 않습니다. TrainingPipeline 전체에 강하게 결합하지 않고,
    해당 메서드를 제공하는 객체라면 테스트용 가짜 객체도 전달할 수 있게 하는 타입 힌트입니다.
    """

    def evaluate(self) -> None:
        """TrainingPipeline.evaluate 메서드와 동일한 계약입니다."""
        ...


def evaluateModel(pipeline: PipelineContext) -> None:
    """동일한 test split에서 두 모델의 mAP, precision, recall을 측정합니다.

    Args:
        pipeline: 실제 단계 로직과 설정, 작업 경로를 가진 TrainingPipeline 호환 객체.

    Returns:
        없음. 처리 결과는 pipelineConfig.yaml에 지정된 workspace와 manifest에 저장됩니다.

    Raises:
        파일 누락, 설정 오류, 모델 추론 실패 등 실제 단계에서 발생한 예외를 그대로 전달합니다.
        예외를 숨기지 않아 자동 실행 시스템이 실패를 감지하고 해당 단계부터 재시도할 수 있습니다.
    """
    pipeline.evaluate()