if __package__:
    from .motor_test import main
else:
    from motor_test import main


if __name__ == "__main__":
    raise SystemExit(main())
