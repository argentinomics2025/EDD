# No default base: preparation must provide the registry-verified digest.
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
WORKDIR /lab
COPY requirements.lock /lab/requirements.lock
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /lab/requirements.lock
COPY runner/ /lab/infra/ec016/runner/
USER 10001:10001
CMD ["python", "-m", "unittest", "-v", "infra.ec016.runner.integration_suite"]
