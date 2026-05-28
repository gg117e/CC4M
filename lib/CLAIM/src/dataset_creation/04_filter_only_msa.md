# Filter real MSA or industrial MSA demo

> Author: Anonymous
> 
> Email: Anonymous

In this filtering step all the repos have been inspected manually in order to only those that contains real MSA
applications or industrial MSA demo. In this classification are included:

- real MSA applications;
- industrial demos that present MSA;
- big-tech related demos that present MSA (like the ones developed by groups of employees of Microsoft, Alibaba, 
Oracle, etc.).

Instead, the following types of repos are not included in the classification:

- non-MSA applications;
- portions or components of MSA applications (like monitors, gateway, etc. for MSA);
- single microservices;
- toy MSA applications;
- academic MSA demo;
- starter kits for MSA applications (even if with predefined microservices);
- template for MSA applications (even if with predefined microservices);
- boilerplate MSA applications (even if with predefined microservices);
- free-time-developed MSA applications/demo;
- examples, tutorials, samples or guides for MSA from books, blogs, articles, sites or lectures;
- non english repository (it could be difficult for us reading documentation and understanding if they really are MSA 
or not);
- repository already considered in the other group (i.e. repository with an "official" ground truth).

The selection has been done by inspecting the GitHub description of the repos and the Readme; in absence of clear clues
about the nature of the repo itself, also additional documentation (like sites) has been inspected; in case of further
doubt, as final ratio, has been inspected the content of the repo (like docker-compose files or the structure of the 
code).

The input file, i.e. the current dataset, is at `../../data/dataset/03_detected_docker.csv`.

The output file, i.e. the only MSA dataset, must be at `../../data/dataset/04_filtered_only_msa.csv`.

<hr>

> reference date: 16/02/2024

Actual filtering results:

| REPO                                                               |   MSA?   | TYPE                         |
|--------------------------------------------------------------------|:--------:|------------------------------|
| https://github.com/1-Platform/one-platform                         | &#10003; |                              |
| https://github.com/BEagle1984/silverback                           |          | MSA infrastructure component |
| https://github.com/DevrexLabs/memstate                             |          | MSA infrastructure component |
| https://github.com/EdwinVW/pitstop                                 |          | Already used                 |
| https://github.com/LeonKou/NetPro                                  |          | Dev tool                     |
| https://github.com/Mikaelemmmm/go-zero-looklook                    |          | Guide                        |
| https://github.com/NTHU-LSALAB/NTHU-Distributed-System             |          | Non-industry demo            |
| https://github.com/OpenCodeFoundation/eSchool                      | &#10003; |                              |
| https://github.com/OpenLMIS/openlmis-ref-distro                    |          | Documentation                |
| https://github.com/OpenLiberty/liberty-bikes                       | &#10003; |                              |
| https://github.com/RobyFerro/go-web                                |          | Framework                    |
| https://github.com/ThoreauZZ/spring-cloud-example                  | &#10003; |                              |
| https://github.com/abpframework/eShopOnAbp                         | &#10003; |                              |
| https://github.com/aidanwhiteley/books                             |          | Non-industry demo            |
| https://github.com/aliyun/alibabacloud-microservice-demo           | &#10003; |                              |
| https://github.com/andeya/erpc                                     |          | Framework                    |
| https://github.com/andrechristikan/ack-nestjs-boilerplate-kafka    |          | Single microservice          |
| https://github.com/apache/apisix-website                           |          | Documentation                |
| https://github.com/asc-lab/micronaut-microservices-poc             | &#10003; |                              |
| https://github.com/authorizerdev/authorizer                        |          | Single microservice          |
| https://github.com/cloudblue/django-cqrs                           |          | Other                        |
| https://github.com/danionescu0/docker-flask-mongodb-example        |          | Non big-industry related     |
| https://github.com/dotnetcore/AgileConfig                          |          | MSA infrastructure component |
| https://github.com/douyu/juno                                      |          | Chinese language             |
| https://github.com/douyu/jupiter                                   |          | Framework                    |
| https://github.com/fabric8-services/fabric8-wit                    |          | Other                        |
| https://github.com/fagongzi/manba                                  |          | MSA infrastructure component |
| https://github.com/fanliang11/surging                              |          | MSA infrastructure component |
| https://github.com/foxmask/django-th                               |          | MSA infrastructure component |
| https://github.com/geoserver/geoserver-cloud                       | &#10003; |                              |
| https://github.com/go-eagle/eagle                                  |          | Framework                    |
| https://github.com/golevelup/nestjs                                |          | Other                        |
| https://github.com/h2non/imaginary                                 |          | Single microservice          |
| https://github.com/harvic3/nodetskeleton                           |          | MSA template                 |
| https://github.com/hellofresh/health-go                            |          | Library                      |
| https://github.com/instana/robot-shop                              | &#10003; |                              |
| https://github.com/ivanpaulovich/clean-architecture-manga          |          | Refactor to monolith         |
| https://github.com/juicycleff/ultimate-backend                     |          | Starter kit                  |
| https://github.com/jvalue/ods                                      | &#10003; |                              |
| https://github.com/kunalkapadia/express-mongoose-es6-rest-api      |          | Boilerplate                  |
| https://github.com/learningOrchestra/mlToolKits                    | &#10003; |                              |
| https://github.com/mailgun/gubernator                              |          | MSA infrastructure component |
| https://github.com/meysamhadeli/booking-microservices              |          | Non-industry demo            |
| https://github.com/microsoft/dotnet-podcasts                       | &#10003; |                              |
| https://github.com/mosn/layotto                                    |          | Dev tool                     |
| https://github.com/nashtech-garage/yas                             |          | Already used                 |
| https://github.com/open-telemetry/opentelemetry-demo               | &#10003; |                              |
| https://github.com/openfaas/faasd                                  |          | MSA infrastructure component |
| https://github.com/pagarme/superbowleto                            |          | Single microservice          |
| https://github.com/phongnguyend/Practical.CleanArchitecture        |          | Other                        |
| https://github.com/pnxtech/hydra-router                            |          | MSA infrastructure component |
| https://github.com/rodrigorodrigues/microservices-design-patterns  |          | Exercise in style            |
| https://github.com/spring-cloud/spring-cloud-consul                |          | MSA component                |
| https://github.com/spring-cloud/spring-cloud-vault                 |          | MSA dev component            |
| https://github.com/spring-cloud/spring-cloud-zookeeper             |          | MSA infrastructure component |
| https://github.com/spring-petclinic/spring-petclinic-microservices |          | Already used                 |
| https://github.com/sqshq/piggymetrics                              |          | Tutorial                     |
| https://github.com/stack-labs/XConf                                |          | Chinese language             |
| https://github.com/stackvana/hook.io                               |          | MSA infrastructure component |
| https://github.com/vanus-labs/vanus                                |          | MSA infrastructure component |
| https://github.com/vietnam-devs/coolstore-microservices            | &#10003; |                              |
| https://github.com/wework/grabbit                                  |          | MSA infrastructure component |