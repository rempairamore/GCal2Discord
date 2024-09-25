
# Contributing to GCal2Discord

Thank you for considering contributing to **GCal2Discord**! We appreciate your help and contributions to improve this project. Please take a few minutes to read through this guide before submitting any contributions.

## How to Contribute

### 1. Fork the Repository

1. Go to the [repository](https://github.com/rempairamore/GCal2Discord) and click the "Fork" button in the top-right corner of the page.
2. Clone the forked repository to your local machine:
   ```bash
   git clone https://github.com/your-username/GCal2Discord.git
   ```
3. Navigate into the project directory:
   ```bash
   cd GCal2Discord
   ```

### 2. Set Up Your Environment

1. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set up the necessary environment variables or the `var.py` file for local development. Refer to the README for setup details.

### 3. Create a Branch for Your Feature/Fix

Create a new branch to work on your changes. Make sure to give it a descriptive name:

```bash
git checkout -b feature/my-awesome-feature
```

### 4. Make Your Changes

- Follow the existing code style and conventions.
- If you're making any major changes, please consider opening an issue first to discuss it.
- Test your changes locally before submitting a pull request.

### 5. Write Meaningful Commit Messages

Write clear and concise commit messages. A good commit message should describe what changed and why.

Examples:
- `Add feature to sync specific calendar events`
- `Fix bug in event creation on Discord`
- `Refactor Google API integration`

### 6. Test Your Changes

Make sure your changes don’t break the project. If possible, add new tests for any added features.

### 7. Push Your Changes

1. Push your changes to your forked repository:
   ```bash
   git push origin feature/my-awesome-feature
   ```

### 8. Submit a Pull Request

1. Go to the original repository on GitHub.
2. Click on the "Pull Requests" tab, then click the "New Pull Request" button.
3. Select the branch you want to merge into (usually `main`) and choose the branch you worked on.
4. Provide a clear and detailed description of what you have done, including the issue number (if applicable).

### 9. Code Review

Your pull request will be reviewed by the project maintainers. You may be asked to make some changes before it can be merged.

## Reporting Bugs and Feature Requests

If you encounter a bug or have a feature request, please open an issue [here](https://github.com/rempairamore/GCal2Discord/issues) and provide as much detail as possible. Include steps to reproduce, error messages, and any other relevant information.


## Style Guide

Please follow these guidelines to ensure consistency in the project:

- Use descriptive variable names.
- Maintain readability: prefer clear code over clever code.
- Document your code where necessary with comments or docstrings.
- Use consistent indentation and formatting (Python PEP 8).

## License

By contributing to this project, you agree that your contributions will be licensed under the same license as the project: **GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007**.

---

Thank you for contributing to GCal2Discord! Every contribution, no matter how small, is appreciated.
