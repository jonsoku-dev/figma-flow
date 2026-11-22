CREATE USER 'littlehands_owner'@'%' IDENTIFIED BY '__LH_OWNER_PASSWORD__';
CREATE USER 'littlehands_runtime'@'%' IDENTIFIED BY '__LH_RUNTIME_PASSWORD__';
GRANT ALL PRIVILEGES ON `littlehands`.* TO 'littlehands_owner'@'%';
