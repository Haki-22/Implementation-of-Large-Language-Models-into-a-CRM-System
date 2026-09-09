# UC-02 live check — ran on: the first 20 corpus messages through the sandwich

Model: codex gpt-5.5 (low); NER bardsai; unify entity
Task: Shrň následující zprávu ze CRM do tří vět. Drž věcný tón, nic nevymýšlej.
Ran: 2026-09-05 20:15, 2 min 33 s

## codex gpt-5.5

    20 of 20 echoed the envelope id on the first attempt       (the correlation wrapper the model must copy back)
    18 of 20 kept every token on the first attempt             (no placeholder dropped or invented)
    22 attempts for 20 messages                                (mean 1.1; retries carry a reminder)
    20 of 20 restored, 0 integrity errors, 0 provider errors   (restored = every token replaced by its value)
    68 of 68 original values in the restored text              (values the model left out of its answer are not a leak, only absent)

codex (gpt-5.5, low) kept the envelope contract on the first attempt for 18 of 20 messages, 20 of 20 came back restored, and 68 of 68 original values reappeared in the restored text.
