from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common.typeinfo import Types
from pyflink.datastream.functions import FlatMapFunction, RuntimeContext


class Tokenizer(FlatMapFunction):
    def flat_map(self, value):
        for word in value.lower().split():
            yield (word, 1)


def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    text = env.from_collection([
        "Apache Flink is cool",
        "PyFlink makes it easy"
    ])

    counts = (
        text.flat_map(Tokenizer(), output_type=Types.TUPLE([Types.STRING(), Types.INT()]))
            .key_by(lambda x: x[0])
            .sum(1)
    )

    counts.print()

    env.execute("Word Count Example")


if __name__ == '__main__':
    main()
