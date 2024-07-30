
RESULTS=()
ERRORS=()

trim () {
    text=$(< /dev/stdin)
    echo -n "$text" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

for result in "$@"; do
    RESULT=$(head -n1 "$result")
    NAME=$(echo $RESULT | cut -d: -f1 | trim)
    EXITCODE=$(echo $RESULT | cut -d: -f2 | trim)
    if [[ $EXITCODE != 0 ]]; then
        ERROR=$(tail -n +2 $result)
        ERRORS+=($ERROR)
    fi
    RESULTS+=("$NAME: $EXITCODE")
done

# echo "${ERRORS[@]}"

for result in "${RESULTS[@]}"; do
    echo "$result"
done
